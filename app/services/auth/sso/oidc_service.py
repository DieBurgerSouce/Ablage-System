"""
OIDC (OpenID Connect) Service.

Implementiert den OIDC Authorization Code Flow:
- Authorization Request
- Token Exchange
- UserInfo Retrieval
- Token Validation

SECURITY:
- PKCE (Proof Key for Code Exchange) standardmaessig aktiviert
- State Parameter für CSRF-Schutz
- Nonce für Replay-Schutz
- Token-Validierung mit JWKS

Unterstützte Provider:
- Microsoft Entra ID (Azure AD)
- Google Workspace
- Okta
- Auth0
- Keycloak
- Beliebige OIDC-kompatible Provider
"""

import structlog
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs
from uuid import UUID

import httpx
from jose import jwt, jwk, JWTError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.sso.sso_config_service import (
    SSOConfigService,
    SSOProviderConfig,
    OIDCConfig,
)
from app.services.auth.sso.sso_state_manager import (
    get_sso_state_manager,
    SSOStateManager,
)

logger = structlog.get_logger(__name__)


class OIDCState(BaseModel):
    """OIDC State für Authorization Flow."""

    state: str = Field(..., description="State Parameter")
    nonce: str = Field(..., description="Nonce für ID Token Validierung")
    code_verifier: Optional[str] = Field(None, description="PKCE Code Verifier")
    provider_id: UUID = Field(..., description="Provider ID")
    redirect_uri: str = Field(..., description="Redirect URI")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=10))


class OIDCTokenResponse(BaseModel):
    """OIDC Token Response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None


class OIDCUserInfo(BaseModel):
    """OIDC UserInfo Claims."""

    sub: str = Field(..., description="Subject Identifier")
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    preferred_username: Optional[str] = None
    picture: Optional[str] = None
    groups: Optional[list] = None
    raw_claims: Dict[str, Any] = Field(default_factory=dict)


class OIDCService:
    """Service für OIDC Authentication."""

    def __init__(
        self,
        db: AsyncSession,
        state_manager: Optional[SSOStateManager] = None,
    ):
        self.db = db
        self.config_service = SSOConfigService(db)
        self.state_manager = state_manager or get_sso_state_manager()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._jwks_cache: Dict[str, Dict[str, Any]] = {}
        self._jwks_cache_time: Dict[str, datetime] = {}

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Lazy HTTP Client Initialisierung."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _generate_code_verifier(self) -> str:
        """Generiert einen PKCE Code Verifier."""
        return secrets.token_urlsafe(64)[:128]

    def _generate_code_challenge(self, verifier: str) -> str:
        """Generiert einen PKCE Code Challenge (S256)."""
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    async def start_authorization(
        self,
        provider_id: UUID,
        company_id: UUID,
        redirect_uri: str,
        additional_params: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str]:
        """
        Startet den OIDC Authorization Flow.

        Args:
            provider_id: Provider-ID
            company_id: Firma-ID
            redirect_uri: Callback-URL
            additional_params: Zusätzliche URL-Parameter

        Returns:
            Tuple aus (authorization_url, state)
        """
        provider = await self.config_service.get_provider(provider_id, company_id)
        if not provider or not provider.oidc_config:
            raise ValueError("OIDC-Provider nicht gefunden oder nicht konfiguriert")

        if not provider.enabled:
            raise ValueError("SSO-Provider ist deaktiviert")

        config = provider.oidc_config

        # Generate security tokens
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = self._generate_code_verifier() if config.use_pkce else None
        code_challenge = self._generate_code_challenge(code_verifier) if code_verifier else None

        # Store state in Redis (multi-worker safe)
        oidc_state = OIDCState(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            provider_id=provider_id,
            redirect_uri=redirect_uri,
        )
        await self.state_manager.store_oidc_state(state, oidc_state)

        # Build authorization URL
        params = {
            "client_id": config.client_id,
            "response_type": config.response_type,
            "scope": " ".join(config.scopes),
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        if additional_params:
            params.update(additional_params)

        auth_url = f"{config.authorization_endpoint}?{urlencode(params)}"

        logger.info(
            "oidc_authorization_started",
            provider_id=str(provider_id),
            state=state[:8] + "...",
        )

        return auth_url, state

    async def handle_callback(
        self,
        code: str,
        state: str,
        company_id: UUID,
    ) -> Tuple[OIDCUserInfo, OIDCTokenResponse]:
        """
        Verarbeitet den OIDC Callback.

        Args:
            code: Authorization Code
            state: State Parameter
            company_id: Firma-ID

        Returns:
            Tuple aus (UserInfo, TokenResponse)
        """
        # Validate state (from Redis, deleted after retrieval for one-time use)
        oidc_state = await self.state_manager.get_oidc_state(state, delete=True)
        if not oidc_state:
            raise ValueError("Ungültiger oder abgelaufener State")

        if datetime.utcnow() > oidc_state.expires_at:
            raise ValueError("Authorization Flow ist abgelaufen")

        # Get provider config
        provider = await self.config_service.get_provider(
            oidc_state.provider_id, company_id
        )
        if not provider or not provider.oidc_config:
            raise ValueError("Provider nicht gefunden")

        config = provider.oidc_config

        # Exchange code for tokens
        tokens = await self._exchange_code(
            config,
            code,
            oidc_state.redirect_uri,
            oidc_state.code_verifier,
        )

        # Validate ID token if present
        if tokens.id_token:
            await self._validate_id_token(
                config, tokens.id_token, oidc_state.nonce
            )

        # Get user info
        user_info = await self._get_userinfo(config, tokens.access_token)

        # Apply claims mapping
        user_info = self._apply_claims_mapping(user_info, config.claims_mapping)

        # Record login
        await self.config_service.record_login(oidc_state.provider_id, company_id)

        logger.info(
            "oidc_callback_successful",
            provider_id=str(oidc_state.provider_id),
            user_sub=user_info.sub[:8] + "...",
        )

        return user_info, tokens

    async def _exchange_code(
        self,
        config: OIDCConfig,
        code: str,
        redirect_uri: str,
        code_verifier: Optional[str],
    ) -> OIDCTokenResponse:
        """Tauscht den Authorization Code gegen Tokens."""
        client = await self._get_http_client()

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.client_id,
        }

        if config.client_secret:
            # Decrypt secret
            encrypted = config.client_secret.get_secret_value()
            decrypted = self.config_service._decrypt_secret(encrypted)
            data["client_secret"] = decrypted

        if code_verifier:
            data["code_verifier"] = code_verifier

        response = await client.post(
            config.token_endpoint,
            data=data,
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            logger.error(
                "oidc_token_exchange_failed",
                status_code=response.status_code,
                error=response.text[:200],
            )
            raise ValueError(f"Token-Austausch fehlgeschlagen: {response.status_code}")

        token_data = response.json()
        return OIDCTokenResponse(**token_data)

    async def _get_jwks(self, config: OIDCConfig) -> Dict[str, Any]:
        """Holt JWKS vom IdP (mit Caching)."""
        if not config.jwks_uri:
            return {}

        cache_key = config.jwks_uri
        now = datetime.utcnow()

        # Check cache (1 hour TTL)
        if cache_key in self._jwks_cache:
            cache_time = self._jwks_cache_time.get(cache_key, datetime.min)
            if (now - cache_time).seconds < 3600:
                return self._jwks_cache[cache_key]

        client = await self._get_http_client()
        response = await client.get(config.jwks_uri)

        if response.status_code != 200:
            logger.warning("jwks_fetch_failed", uri=config.jwks_uri)
            return self._jwks_cache.get(cache_key, {})

        jwks = response.json()
        self._jwks_cache[cache_key] = jwks
        self._jwks_cache_time[cache_key] = now

        return jwks

    async def _validate_id_token(
        self, config: OIDCConfig, id_token: str, nonce: str
    ) -> Dict[str, Any]:
        """Validiert das ID Token."""
        # Get JWKS for validation
        jwks = await self._get_jwks(config)

        try:
            # Decode header to get kid
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")

            # Find matching key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break

            if not key:
                # Try without kid matching
                if jwks.get("keys"):
                    key = jwks["keys"][0]

            if key:
                # Validate with key
                claims = jwt.decode(
                    id_token,
                    key,
                    algorithms=["RS256", "ES256"],
                    audience=config.client_id,
                    issuer=config.issuer,
                    options={"verify_at_hash": False},
                )
            else:
                # SECURITY FIX: Do NOT decode without verification (CWE-347)
                # Accepting unverified tokens allows authentication bypass
                logger.error(
                    "id_token_validation_failed",
                    reason="no_matching_jwks_key",
                    kid=kid,
                )
                raise ValueError(
                    "ID Token konnte nicht validiert werden: Kein passender JWKS-Schlüssel gefunden"
                )

            # Validate nonce
            if claims.get("nonce") != nonce:
                raise ValueError("Nonce stimmt nicht überein")

            return claims

        except JWTError as e:
            logger.error("id_token_validation_failed", error=str(e))
            raise ValueError(f"ID Token Validierung fehlgeschlagen: {e}")

    async def _get_userinfo(
        self, config: OIDCConfig, access_token: str
    ) -> OIDCUserInfo:
        """Holt UserInfo vom IdP."""
        if not config.userinfo_endpoint:
            # Try to extract from ID token claims
            return OIDCUserInfo(sub="unknown", raw_claims={})

        client = await self._get_http_client()
        response = await client.get(
            config.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            logger.warning(
                "userinfo_fetch_failed",
                status_code=response.status_code,
            )
            return OIDCUserInfo(sub="unknown", raw_claims={})

        claims = response.json()
        return OIDCUserInfo(
            sub=claims.get("sub", ""),
            email=claims.get("email"),
            email_verified=claims.get("email_verified"),
            name=claims.get("name"),
            given_name=claims.get("given_name"),
            family_name=claims.get("family_name"),
            preferred_username=claims.get("preferred_username"),
            picture=claims.get("picture"),
            groups=claims.get("groups"),
            raw_claims=claims,
        )

    def _apply_claims_mapping(
        self, user_info: OIDCUserInfo, mapping: Dict[str, str]
    ) -> OIDCUserInfo:
        """Wendet das Claims Mapping an."""
        raw = user_info.raw_claims

        for target, source in mapping.items():
            if source in raw and hasattr(user_info, target):
                setattr(user_info, target, raw[source])

        return user_info

    async def refresh_token(
        self,
        provider_id: UUID,
        company_id: UUID,
        refresh_token: str,
    ) -> OIDCTokenResponse:
        """Erneuert Access Token mit Refresh Token."""
        provider = await self.config_service.get_provider(provider_id, company_id)
        if not provider or not provider.oidc_config:
            raise ValueError("Provider nicht gefunden")

        config = provider.oidc_config
        client = await self._get_http_client()

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id,
        }

        if config.client_secret:
            encrypted = config.client_secret.get_secret_value()
            decrypted = self.config_service._decrypt_secret(encrypted)
            data["client_secret"] = decrypted

        response = await client.post(
            config.token_endpoint,
            data=data,
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            raise ValueError("Token-Refresh fehlgeschlagen")

        return OIDCTokenResponse(**response.json())

    async def logout_url(
        self,
        provider_id: UUID,
        company_id: UUID,
        id_token_hint: Optional[str] = None,
        post_logout_redirect_uri: Optional[str] = None,
    ) -> Optional[str]:
        """Generiert die Logout-URL (falls vom IdP unterstützt)."""
        provider = await self.config_service.get_provider(provider_id, company_id)
        if not provider or not provider.oidc_config:
            return None

        # Standard OIDC end session endpoint
        # This would need to be configured per provider
        config = provider.oidc_config
        end_session_endpoint = config.authorization_endpoint.replace(
            "/authorize", "/logout"
        ).replace("/oauth2/v2.0/authorize", "/oauth2/v2.0/logout")

        params = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri

        if params:
            return f"{end_session_endpoint}?{urlencode(params)}"
        return end_session_endpoint

    async def close(self):
        """Schließt HTTP-Client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

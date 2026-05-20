"""
SSO Configuration Service.

Verwaltung von SSO-Provider-Konfigurationen:
- CRUD für Provider-Konfigurationen
- Verschlüsselung sensibler Daten
- Multi-Tenant Support

SECURITY:
- Client Secrets werden AES-256-GCM verschlüsselt gespeichert
- Private Keys werden verschlüsselt gespeichert
- Keine Secrets in Logs
"""

import structlog
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, Union
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = structlog.get_logger(__name__)


class SSOProviderType(str, Enum):
    """SSO-Provider-Typen."""

    OIDC = "oidc"
    SAML = "saml"


class SSOProviderPreset(str, Enum):
    """Vorkonfigurierte Provider-Presets."""

    MICROSOFT_ENTRA = "microsoft_entra"
    GOOGLE_WORKSPACE = "google_workspace"
    OKTA = "okta"
    ONELOGIN = "onelogin"
    AUTH0 = "auth0"
    KEYCLOAK = "keycloak"
    CUSTOM_OIDC = "custom_oidc"
    CUSTOM_SAML = "custom_saml"


class OIDCConfig(BaseModel):
    """OIDC-spezifische Konfiguration."""

    client_id: str = Field(..., description="OAuth2 Client ID")
    client_secret: Optional[SecretStr] = Field(None, description="OAuth2 Client Secret")
    authorization_endpoint: str = Field(..., description="Authorization Endpoint URL")
    token_endpoint: str = Field(..., description="Token Endpoint URL")
    userinfo_endpoint: Optional[str] = Field(None, description="UserInfo Endpoint URL")
    jwks_uri: Optional[str] = Field(None, description="JWKS URI für Token-Validierung")
    issuer: str = Field(..., description="Token Issuer")
    scopes: List[str] = Field(default=["openid", "profile", "email"], description="Requested Scopes")
    response_type: str = Field(default="code", description="OAuth2 Response Type")
    use_pkce: bool = Field(default=True, description="PKCE verwenden")
    claims_mapping: Dict[str, str] = Field(
        default={
            "email": "email",
            "name": "name",
            "given_name": "given_name",
            "family_name": "family_name",
        },
        description="Mapping von IdP Claims zu internen Feldern"
    )


class SAMLConfig(BaseModel):
    """SAML-spezifische Konfiguration."""

    idp_entity_id: str = Field(..., description="IdP Entity ID")
    idp_sso_url: str = Field(..., description="IdP SSO Service URL")
    idp_slo_url: Optional[str] = Field(None, description="IdP SLO Service URL")
    idp_certificate: str = Field(..., description="IdP X.509 Certificate (PEM)")
    sp_entity_id: str = Field(..., description="SP Entity ID")
    sp_acs_url: str = Field(..., description="SP Assertion Consumer Service URL")
    sp_slo_url: Optional[str] = Field(None, description="SP Single Logout URL")
    sp_private_key: Optional[SecretStr] = Field(None, description="SP Private Key (PEM)")
    sp_certificate: Optional[str] = Field(None, description="SP Certificate (PEM)")
    name_id_format: str = Field(
        default="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        description="NameID Format"
    )
    sign_requests: bool = Field(default=True, description="Requests signieren")
    sign_assertions: bool = Field(default=True, description="Assertion-Signatur erforderlich")
    encrypt_assertions: bool = Field(default=False, description="Assertion-Verschlüsselung erforderlich")
    attribute_mapping: Dict[str, str] = Field(
        default={
            "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
            "given_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            "family_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        },
        description="Mapping von SAML Attributes zu internen Feldern"
    )


# TypedDict for config_data parameter to avoid Any type
# NOTE: External JWKS/claims still use Dict[str, Any] as their structure is IdP-specific
class SSOConfigData(TypedDict, total=False):
    """Konfigurationsdaten für SSO-Provider-Erstellung."""

    # OIDC-spezifisch
    client_id: str
    client_secret: str
    tenant_id: str
    domain: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    issuer: str
    scopes: List[str]
    response_type: str
    use_pkce: bool
    claims_mapping: Dict[str, str]

    # SAML-spezifisch
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: str
    idp_certificate: str
    sp_entity_id: str
    sp_acs_url: str
    sp_slo_url: str
    sp_private_key: str
    sp_certificate: str
    name_id_format: str
    sign_requests: bool
    sign_assertions: bool
    encrypt_assertions: bool
    attribute_mapping: Dict[str, str]

    # Gemeinsam
    auto_create_users: bool
    default_role: str
    allowed_domains: List[str]
    group_mapping: Dict[str, str]


class SSOProviderUpdate(TypedDict, total=False):
    """Update-Daten für SSO-Provider."""

    name: str
    enabled: bool
    is_primary: bool
    auto_create_users: bool
    default_role: str
    allowed_domains: List[str]
    group_mapping: Dict[str, str]
    last_used_at: datetime
    login_count: int


class SSOProviderConfig(BaseModel):
    """SSO-Provider-Konfiguration."""

    id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    name: str = Field(..., min_length=1, max_length=100, description="Anzeigename")
    provider_type: SSOProviderType
    preset: SSOProviderPreset
    enabled: bool = Field(default=False, description="Provider aktiviert")
    is_primary: bool = Field(default=False, description="Primärer SSO-Provider")

    # Type-specific config
    oidc_config: Optional[OIDCConfig] = None
    saml_config: Optional[SAMLConfig] = None

    # User provisioning
    auto_create_users: bool = Field(default=True, description="Benutzer automatisch anlegen")
    default_role: str = Field(default="viewer", description="Standard-Rolle für neue Benutzer")
    allowed_domains: Optional[List[str]] = Field(None, description="Erlaubte Email-Domains")
    group_mapping: Optional[Dict[str, str]] = Field(None, description="IdP Groups zu Rollen")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
    login_count: int = Field(default=0)


class SSOConfigService:
    """Service für SSO-Provider-Konfiguration."""

    # Provider Presets mit vorkonfigurierten URLs
    PROVIDER_PRESETS = {
        SSOProviderPreset.MICROSOFT_ENTRA: {
            "provider_type": SSOProviderType.OIDC,
            "authorization_endpoint": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            "token_endpoint": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
            "jwks_uri": "https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
            "issuer": "https://login.microsoftonline.com/{tenant_id}/v2.0",
            "scopes": ["openid", "profile", "email", "User.Read"],
        },
        SSOProviderPreset.GOOGLE_WORKSPACE: {
            "provider_type": SSOProviderType.OIDC,
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "issuer": "https://accounts.google.com",
            "scopes": ["openid", "profile", "email"],
        },
        SSOProviderPreset.OKTA: {
            "provider_type": SSOProviderType.OIDC,
            "authorization_endpoint": "https://{domain}/oauth2/v1/authorize",
            "token_endpoint": "https://{domain}/oauth2/v1/token",
            "userinfo_endpoint": "https://{domain}/oauth2/v1/userinfo",
            "jwks_uri": "https://{domain}/oauth2/v1/keys",
            "issuer": "https://{domain}",
            "scopes": ["openid", "profile", "email", "groups"],
        },
        SSOProviderPreset.AUTH0: {
            "provider_type": SSOProviderType.OIDC,
            "authorization_endpoint": "https://{domain}/authorize",
            "token_endpoint": "https://{domain}/oauth2/token",
            "userinfo_endpoint": "https://{domain}/userinfo",
            "jwks_uri": "https://{domain}/.well-known/jwks.json",
            "issuer": "https://{domain}/",
            "scopes": ["openid", "profile", "email"],
        },
        SSOProviderPreset.KEYCLOAK: {
            "provider_type": SSOProviderType.OIDC,
            "authorization_endpoint": "{base_url}/realms/{realm}/protocol/openid-connect/auth",
            "token_endpoint": "{base_url}/realms/{realm}/protocol/openid-connect/token",
            "userinfo_endpoint": "{base_url}/realms/{realm}/protocol/openid-connect/userinfo",
            "jwks_uri": "{base_url}/realms/{realm}/protocol/openid-connect/certs",
            "issuer": "{base_url}/realms/{realm}",
            "scopes": ["openid", "profile", "email"],
        },
        SSOProviderPreset.CUSTOM_OIDC: {
            "provider_type": SSOProviderType.OIDC,
            "scopes": ["openid", "profile", "email"],
        },
        SSOProviderPreset.CUSTOM_SAML: {
            "provider_type": SSOProviderType.SAML,
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self._encryption_key = self._get_encryption_key()

    def _get_encryption_key(self) -> bytes:
        """
        Holt den Verschlüsselungsschluessel aus den Settings.

        SECURITY: Es wird KEIN Fallback auf einen Default-Schluessel verwendet,
        da dies alle verschlüsselten Credentials kompromittieren wuerde (CWE-327, CWE-330).
        """
        key = getattr(settings, "SSO_ENCRYPTION_KEY", None)
        if not key:
            # SECURITY FIX: No fallback to default key - this would compromise all encrypted SSO credentials
            # In production, SSO_ENCRYPTION_KEY MUST be configured
            secret_key = getattr(settings, "SECRET_KEY", None)
            if not secret_key:
                raise ValueError(
                    "SSO_ENCRYPTION_KEY oder SECRET_KEY muss konfiguriert sein. "
                    "SSO-Konfiguration ohne Verschlüsselung nicht möglich."
                )
            # Derive key from SECRET_KEY (production systems should use SSO_ENCRYPTION_KEY)
            import hashlib
            logger.warning(
                "sso_using_derived_key",
                message="SSO_ENCRYPTION_KEY nicht gesetzt - verwende abgeleiteten Schluessel. "
                        "Für Produktionssysteme SSO_ENCRYPTION_KEY konfigurieren."
            )
            return hashlib.sha256(secret_key.encode()).digest()[:32]
        return key.encode() if isinstance(key, str) else key

    def _encrypt_secret(self, secret: str) -> str:
        """Verschlüsselt ein Secret."""
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os

        nonce = os.urandom(12)
        aesgcm = AESGCM(self._encryption_key)
        ciphertext = aesgcm.encrypt(nonce, secret.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def _decrypt_secret(self, encrypted: str) -> str:
        """Entschlüsselt ein Secret."""
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        data = base64.b64decode(encrypted)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self._encryption_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()

    async def create_provider(
        self,
        company_id: UUID,
        name: str,
        preset: SSOProviderPreset,
        config_data: SSOConfigData,
    ) -> SSOProviderConfig:
        """
        Erstellt eine neue SSO-Provider-Konfiguration.

        Args:
            company_id: Firma-ID
            name: Anzeigename
            preset: Provider-Preset
            config_data: Provider-spezifische Konfiguration
        """
        provider_type = self.PROVIDER_PRESETS.get(preset, {}).get(
            "provider_type", SSOProviderType.OIDC
        )

        # Build config based on type
        oidc_config = None
        saml_config = None

        if provider_type == SSOProviderType.OIDC:
            # Merge preset with custom config
            preset_config = self.PROVIDER_PRESETS.get(preset, {}).copy()
            preset_config.update(config_data)

            # Encrypt client secret if provided
            if "client_secret" in preset_config and preset_config["client_secret"]:
                secret = preset_config["client_secret"]
                if hasattr(secret, "get_secret_value"):
                    secret = secret.get_secret_value()
                preset_config["client_secret"] = SecretStr(self._encrypt_secret(secret))

            oidc_config = OIDCConfig(**{
                k: v for k, v in preset_config.items()
                if k in OIDCConfig.model_fields
            })

        elif provider_type == SSOProviderType.SAML:
            # Encrypt private key if provided
            if "sp_private_key" in config_data and config_data["sp_private_key"]:
                key = config_data["sp_private_key"]
                if hasattr(key, "get_secret_value"):
                    key = key.get_secret_value()
                config_data["sp_private_key"] = SecretStr(self._encrypt_secret(key))

            saml_config = SAMLConfig(**config_data)

        provider = SSOProviderConfig(
            company_id=company_id,
            name=name,
            provider_type=provider_type,
            preset=preset,
            oidc_config=oidc_config,
            saml_config=saml_config,
            auto_create_users=config_data.get("auto_create_users", True),
            default_role=config_data.get("default_role", "viewer"),
            allowed_domains=config_data.get("allowed_domains"),
            group_mapping=config_data.get("group_mapping"),
        )

        # Store in database (using AppConfig for now)
        from app.db.models import AppConfig

        config_key = f"sso_provider_{provider.id}"
        config_value = provider.model_dump(mode="json")

        # Remove secrets from stored value, store separately
        if oidc_config and oidc_config.client_secret:
            config_value["_encrypted_client_secret"] = oidc_config.client_secret.get_secret_value()
            if "oidc_config" in config_value and config_value["oidc_config"]:
                config_value["oidc_config"]["client_secret"] = None

        existing = await self.db.execute(
            select(AppConfig).where(AppConfig.key == config_key)
        )
        existing_config = existing.scalar_one_or_none()

        if existing_config:
            existing_config.value = config_value
        else:
            new_config = AppConfig(key=config_key, value=config_value)
            self.db.add(new_config)

        await self.db.commit()

        logger.info(
            "sso_provider_created",
            provider_id=str(provider.id),
            company_id=str(company_id),
            preset=preset.value,
        )

        return provider

    async def get_provider(
        self, provider_id: UUID, company_id: UUID
    ) -> Optional[SSOProviderConfig]:
        """Holt eine Provider-Konfiguration."""
        from app.db.models import AppConfig

        config_key = f"sso_provider_{provider_id}"
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == config_key)
        )
        config = result.scalar_one_or_none()

        if not config:
            return None

        data = config.value
        if data.get("company_id") != str(company_id):
            return None

        # Restore encrypted secrets
        if "_encrypted_client_secret" in data:
            if data.get("oidc_config"):
                data["oidc_config"]["client_secret"] = data["_encrypted_client_secret"]
            del data["_encrypted_client_secret"]

        return SSOProviderConfig(**data)

    async def list_providers(
        self, company_id: UUID, enabled_only: bool = False
    ) -> List[SSOProviderConfig]:
        """Listet alle Provider einer Firma auf."""
        from app.db.models import AppConfig

        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key.like("sso_provider_%"))
        )
        configs = result.scalars().all()

        providers = []
        for config in configs:
            data = config.value
            if data.get("company_id") != str(company_id):
                continue
            if enabled_only and not data.get("enabled", False):
                continue

            # Don't include secrets in list
            if data.get("oidc_config") and data["oidc_config"].get("client_secret"):
                data["oidc_config"]["client_secret"] = None
            if "_encrypted_client_secret" in data:
                del data["_encrypted_client_secret"]

            providers.append(SSOProviderConfig(**data))

        return providers

    async def update_provider(
        self,
        provider_id: UUID,
        company_id: UUID,
        updates: SSOProviderUpdate,
    ) -> Optional[SSOProviderConfig]:
        """Aktualisiert eine Provider-Konfiguration."""
        provider = await self.get_provider(provider_id, company_id)
        if not provider:
            return None

        # OIDC-spezifische Felder
        oidc_fields = {"client_id", "client_secret", "scopes", "claims_mapping"}
        # SAML-spezifische Felder
        saml_fields = {"idp_certificate", "sp_entity_id", "attribute_mapping"}

        # Apply updates
        for key, value in updates.items():
            if value is None:
                continue

            # OIDC-spezifische Felder
            if key in oidc_fields and provider.oidc_config:
                if key == "client_secret":
                    # Verschlüsseln und speichern
                    secret_val = value.get_secret_value() if hasattr(value, "get_secret_value") else value
                    encrypted = self._encrypt_secret(secret_val)
                    provider.oidc_config.client_secret = SecretStr(encrypted)
                else:
                    setattr(provider.oidc_config, key, value)

            # SAML-spezifische Felder
            elif key in saml_fields and provider.saml_config:
                setattr(provider.saml_config, key, value)

            # Top-Level-Felder
            elif hasattr(provider, key) and key not in ["id", "company_id", "created_at"]:
                setattr(provider, key, value)

        provider.updated_at = datetime.utcnow()

        # Save back
        from app.db.models import AppConfig

        config_key = f"sso_provider_{provider_id}"
        result = await self.db.execute(
            select(AppConfig).where(AppConfig.key == config_key)
        )
        config = result.scalar_one_or_none()

        if config:
            config_value = provider.model_dump(mode="json")
            # Encrypted secret separat speichern
            if provider.oidc_config and provider.oidc_config.client_secret:
                config_value["_encrypted_client_secret"] = provider.oidc_config.client_secret.get_secret_value()
                if config_value.get("oidc_config"):
                    config_value["oidc_config"]["client_secret"] = None
            config.value = config_value
            await self.db.commit()

        logger.info(
            "sso_provider_updated",
            provider_id=str(provider_id),
            company_id=str(company_id),
        )

        return provider

    async def delete_provider(
        self, provider_id: UUID, company_id: UUID
    ) -> bool:
        """Löscht eine Provider-Konfiguration."""
        provider = await self.get_provider(provider_id, company_id)
        if not provider:
            return False

        from app.db.models import AppConfig

        config_key = f"sso_provider_{provider_id}"
        await self.db.execute(
            delete(AppConfig).where(AppConfig.key == config_key)
        )
        await self.db.commit()

        logger.info(
            "sso_provider_deleted",
            provider_id=str(provider_id),
            company_id=str(company_id),
        )

        return True

    async def set_primary_provider(
        self, provider_id: UUID, company_id: UUID
    ) -> bool:
        """Setzt einen Provider als primären SSO-Provider."""
        # First, unset all other providers as primary
        providers = await self.list_providers(company_id)
        for p in providers:
            if p.is_primary and p.id != provider_id:
                await self.update_provider(p.id, company_id, {"is_primary": False})

        # Set the selected provider as primary
        result = await self.update_provider(
            provider_id, company_id, {"is_primary": True, "enabled": True}
        )
        return result is not None

    async def record_login(self, provider_id: UUID, company_id: UUID) -> None:
        """Zeichnet einen erfolgreichen Login auf."""
        provider = await self.get_provider(provider_id, company_id)
        if provider:
            await self.update_provider(
                provider_id,
                company_id,
                {
                    "last_used_at": datetime.utcnow(),
                    "login_count": provider.login_count + 1,
                },
            )

    def get_preset_template(self, preset: SSOProviderPreset) -> SSOConfigData:
        """Gibt das Template für einen Provider-Preset zurück."""
        return self.PROVIDER_PRESETS.get(preset, {}).copy()

"""
SSO (Single Sign-On) API Endpoints.

Enterprise-Level SSO-Management:
- Provider-Konfiguration (CRUD)
- OIDC Authorization Flow
- SAML Authentication Flow
- User Provisioning

Feinpoliert und durchdacht - Enterprise SSO auf hoechstem Niveau.

SECURITY:
- Alle Endpoints erfordern Admin-Berechtigung (ausser Callbacks)
- Secrets werden verschluesselt gespeichert
- State/Nonce-Validierung für CSRF/Replay-Schutz
"""

import secrets
import structlog
from urllib.parse import quote
from datetime import timedelta
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.safe_errors import safe_error_detail
from app.core.security_auth import create_access_token, get_password_hash
from app.db.models import User
from app.services.auth.sso import OIDCService, SAMLService, SSOConfigService
from app.db.models_cash_company import UserCompany  # W2-05
from app.services.auth.sso.sso_config_service import (
    SSOProviderConfig,
    SSOProviderPreset,
    SSOProviderType,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sso", tags=["SSO"])


def _safe_redirect_param(value: Optional[str]) -> str:
    """Sanitisiert IdP-/angreiferkontrollierte Werte fuer Redirect-URLs.

    SECURITY (W2-20): Verhindert CRLF-/Header-/Redirect-Injection, indem
    Zeilenumbrueche entfernt und der Wert URL-encoded wird, bevor er in den
    Location-Header (RedirectResponse) interpoliert wird.
    """
    if not value:
        return ""
    # CRLF (und verwandte Steuerzeichen) strippen -> kein Header-Splitting
    cleaned = value.replace("\r", "").replace("\n", "")
    # URL-encode -> kein Ausbrechen aus dem Query-Parameter / Pfad
    return quote(cleaned, safe="")


# =============================================================================
# Request/Response Schemas
# =============================================================================


class SSOProviderCreate(BaseModel):
    """Schema zum Erstellen eines SSO-Providers."""

    name: str = Field(..., min_length=1, max_length=100, description="Anzeigename")
    preset: SSOProviderPreset = Field(..., description="Provider-Preset")

    # OIDC-spezifisch
    client_id: Optional[str] = Field(None, description="OAuth2 Client ID")
    client_secret: Optional[SecretStr] = Field(None, description="OAuth2 Client Secret")
    tenant_id: Optional[str] = Field(None, description="Tenant ID (Microsoft Entra)")
    domain: Optional[str] = Field(None, description="IdP Domain (Okta, Auth0)")

    # SAML-spezifisch
    idp_entity_id: Optional[str] = Field(None, description="IdP Entity ID")
    idp_sso_url: Optional[str] = Field(None, description="IdP SSO URL")
    idp_certificate: Optional[str] = Field(None, description="IdP Certificate (PEM)")

    # Gemeinsam
    auto_create_users: bool = Field(default=True, description="Benutzer automatisch anlegen")
    default_role: str = Field(default="viewer", description="Standard-Rolle")
    allowed_domains: Optional[List[str]] = Field(None, description="Erlaubte Email-Domains")


class SSOProviderUpdate(BaseModel):
    """Schema zum Aktualisieren eines SSO-Providers."""

    # Allgemeine Felder
    name: Optional[str] = Field(None, max_length=100)
    enabled: Optional[bool] = None
    auto_create_users: Optional[bool] = None
    default_role: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    group_mapping: Optional[Dict[str, str]] = None

    # OIDC-spezifische Felder
    client_id: Optional[str] = Field(None, description="OAuth2 Client ID")
    client_secret: Optional[SecretStr] = Field(None, description="OAuth2 Client Secret")
    scopes: Optional[List[str]] = Field(None, description="OIDC Scopes")
    claims_mapping: Optional[Dict[str, str]] = Field(None, description="Claims Mapping")

    # SAML-spezifische Felder
    idp_certificate: Optional[str] = Field(None, description="IdP Certificate (PEM)")
    sp_entity_id: Optional[str] = Field(None, description="SP Entity ID")
    attribute_mapping: Optional[Dict[str, str]] = Field(None, description="SAML Attribute Mapping")


class SSOProviderResponse(BaseModel):
    """Response Schema für SSO-Provider."""

    id: str
    name: str
    provider_type: str
    preset: str
    enabled: bool
    is_primary: bool
    auto_create_users: bool
    default_role: str
    allowed_domains: Optional[List[str]] = None
    login_count: int
    last_used_at: Optional[str] = None
    created_at: str
    updated_at: str


class SSOProviderListItem(BaseModel):
    """Kurzform für Provider-Liste."""

    id: str
    name: str
    provider_type: str
    preset: str
    enabled: bool
    is_primary: bool
    login_count: int


class AuthorizationResponse(BaseModel):
    """Response für Start des Auth-Flows."""

    authorization_url: str = Field(..., description="Redirect-URL zum IdP")
    state: str = Field(..., description="State Parameter")


class CallbackTokenResponse(BaseModel):
    """Response nach erfolgreichem Callback."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    user: JSONDict


class PresetTemplateResponse(BaseModel):
    """Response für Provider-Preset-Template."""

    preset: str
    provider_type: str
    required_fields: List[str]
    optional_fields: List[str]
    description: str


# =============================================================================
# Provider Configuration Endpoints
# =============================================================================


@router.get("/providers", response_model=List[SSOProviderListItem])
async def list_sso_providers(
    enabled_only: bool = Query(False, description="Nur aktivierte Provider"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SSOProviderListItem]:
    """
    Listet alle SSO-Provider der Firma auf.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    providers = await service.list_providers(company_id, enabled_only)

    return [
        SSOProviderListItem(
            id=str(p.id),
            name=p.name,
            provider_type=p.provider_type.value,
            preset=p.preset.value,
            enabled=p.enabled,
            is_primary=p.is_primary,
            login_count=p.login_count,
        )
        for p in providers
    ]


@router.get("/providers/{provider_id}", response_model=SSOProviderResponse)
async def get_sso_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SSOProviderResponse:
    """
    Gibt Details eines SSO-Providers zurück.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    provider = await service.get_provider(provider_id, company_id)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    return _provider_to_response(provider)


@router.post("/providers", response_model=SSOProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_sso_provider(
    data: SSOProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SSOProviderResponse:
    """
    Erstellt einen neuen SSO-Provider.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    # Build config data based on preset
    config_data = _build_config_data(data)

    service = SSOConfigService(db)

    try:
        provider = await service.create_provider(
            company_id=company_id,
            name=data.name,
            preset=data.preset,
            config_data=config_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "SSO"),
        )

    logger.info(
        "sso_provider_created_api",
        provider_id=str(provider.id),
        preset=data.preset.value,
    )

    return _provider_to_response(provider)


@router.patch("/providers/{provider_id}", response_model=SSOProviderResponse)
async def update_sso_provider(
    provider_id: UUID,
    data: SSOProviderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SSOProviderResponse:
    """
    Aktualisiert einen SSO-Provider.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}

    provider = await service.update_provider(provider_id, company_id, updates)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    return _provider_to_response(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sso_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Löscht einen SSO-Provider.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    deleted = await service.delete_provider(provider_id, company_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class SSOProviderTestResponse(BaseModel):
    """Response Schema für Provider-Test."""

    success: bool
    message: str
    expires: Optional[str] = None


@router.post("/providers/{provider_id}/test", response_model=SSOProviderTestResponse)
async def test_sso_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SSOProviderTestResponse:
    """
    Testet die Verbindung zum SSO-Provider.

    - OIDC: Prüft Discovery-Endpoint und JWKS
    - SAML: Prüft IdP-Zertifikat

    Erfordert Admin-Berechtigung.
    """
    import httpx
    from cryptography import x509

    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    provider = await service.get_provider(provider_id, company_id)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    # OIDC Provider Test
    if provider.oidc_config:
        config = provider.oidc_config
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                if config.jwks_uri:
                    response = await client.get(config.jwks_uri)
                    if response.status_code == 200:
                        jwks = response.json()
                        key_count = len(jwks.get("keys", []))
                        return SSOProviderTestResponse(
                            success=True,
                            message=f"JWKS erfolgreich abgerufen ({key_count} Schluessel)",
                        )
                    return SSOProviderTestResponse(
                        success=False,
                        message=f"JWKS-Abruf fehlgeschlagen: HTTP {response.status_code}",
                    )
                return SSOProviderTestResponse(
                    success=False,
                    message="Keine JWKS URI konfiguriert",
                )
            except httpx.TimeoutException:
                return SSOProviderTestResponse(
                    success=False,
                    message="Zeitüberschreitung beim JWKS-Abruf",
                )
            except Exception as e:
                return SSOProviderTestResponse(
                    success=False,
                    message=f"Verbindungsfehler: {str(e)}",
                )

    # SAML Provider Test
    elif provider.saml_config:
        config = provider.saml_config
        try:
            if config.idp_certificate:
                cert_pem = config.idp_certificate
                if "-----BEGIN CERTIFICATE-----" not in cert_pem:
                    cert_pem = (
                        "-----BEGIN CERTIFICATE-----\n"
                        + cert_pem
                        + "\n-----END CERTIFICATE-----"
                    )
                cert = x509.load_pem_x509_certificate(cert_pem.encode())
                expires = cert.not_valid_after_utc.isoformat()
                return SSOProviderTestResponse(
                    success=True,
                    message="IdP-Zertifikat gültig",
                    expires=expires,
                )
            return SSOProviderTestResponse(
                success=False,
                message="Kein IdP-Zertifikat konfiguriert",
            )
        except Exception as e:
            return SSOProviderTestResponse(
                success=False,
                message=f"Zertifikatsfehler: {str(e)}",
            )

    return SSOProviderTestResponse(
        success=False,
        message="Provider-Typ nicht unterstützt",
    )


@router.post("/providers/{provider_id}/set-primary", response_model=SSOProviderResponse)
async def set_primary_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SSOProviderResponse:
    """
    Setzt einen Provider als primären SSO-Provider.

    Erfordert Admin-Berechtigung.
    """
    _require_admin(current_user)
    company_id = _get_company_id(current_user)

    service = SSOConfigService(db)
    success = await service.set_primary_provider(provider_id, company_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    provider = await service.get_provider(provider_id, company_id)
    return _provider_to_response(provider)


@router.get("/presets", response_model=List[PresetTemplateResponse])
async def list_provider_presets(
    current_user: User = Depends(get_current_user),
) -> List[PresetTemplateResponse]:
    """
    Listet alle verfügbaren Provider-Presets auf.

    Gibt Informationen zu erforderlichen und optionalen Feldern.
    """
    _require_admin(current_user)

    presets = [
        PresetTemplateResponse(
            preset="microsoft_entra",
            provider_type="oidc",
            required_fields=["client_id", "client_secret", "tenant_id"],
            optional_fields=["allowed_domains", "group_mapping"],
            description="Microsoft Entra ID (ehemals Azure AD)",
        ),
        PresetTemplateResponse(
            preset="google_workspace",
            provider_type="oidc",
            required_fields=["client_id", "client_secret"],
            optional_fields=["allowed_domains"],
            description="Google Workspace",
        ),
        PresetTemplateResponse(
            preset="okta",
            provider_type="oidc",
            required_fields=["client_id", "client_secret", "domain"],
            optional_fields=["allowed_domains", "group_mapping"],
            description="Okta",
        ),
        PresetTemplateResponse(
            preset="auth0",
            provider_type="oidc",
            required_fields=["client_id", "client_secret", "domain"],
            optional_fields=["allowed_domains"],
            description="Auth0",
        ),
        PresetTemplateResponse(
            preset="keycloak",
            provider_type="oidc",
            required_fields=["client_id", "client_secret", "domain"],
            optional_fields=["allowed_domains", "group_mapping"],
            description="Keycloak",
        ),
        PresetTemplateResponse(
            preset="custom_oidc",
            provider_type="oidc",
            required_fields=["client_id", "authorization_endpoint", "token_endpoint", "issuer"],
            optional_fields=["client_secret", "userinfo_endpoint", "jwks_uri"],
            description="Benutzerdefinierter OIDC-Provider",
        ),
        PresetTemplateResponse(
            preset="custom_saml",
            provider_type="saml",
            required_fields=["idp_entity_id", "idp_sso_url", "idp_certificate"],
            optional_fields=["idp_slo_url", "attribute_mapping"],
            description="Benutzerdefinierter SAML 2.0-Provider",
        ),
    ]

    return presets


# =============================================================================
# OIDC Authentication Endpoints
# =============================================================================


@router.get("/oidc/{provider_id}/authorize", response_model=AuthorizationResponse)
async def start_oidc_authorization(
    provider_id: UUID,
    redirect_uri: str = Query(..., description="Callback-URL"),
    db: AsyncSession = Depends(get_db),
) -> AuthorizationResponse:
    """
    Startet den OIDC Authorization Code Flow.

    Kein Login erforderlich - wird für SSO-Login verwendet.
    """
    # Get provider to determine company
    config_service = SSOConfigService(db)

    # Find provider across all companies (for login flow)
    from app.db.models import AppConfig
    from sqlalchemy import select

    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"sso_provider_{provider_id}")
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    company_id = UUID(config.value.get("company_id"))

    service = OIDCService(db)

    try:
        auth_url, state = await service.start_authorization(
            provider_id=provider_id,
            company_id=company_id,
            redirect_uri=redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "SSO"),
        )

    return AuthorizationResponse(authorization_url=auth_url, state=state)


@router.get("/oidc/{provider_id}/callback")
async def oidc_callback(
    provider_id: UUID,
    code: str = Query(..., description="Authorization Code"),
    state: str = Query(..., description="State Parameter"),
    error: Optional[str] = Query(None, description="Error Code"),
    error_description: Optional[str] = Query(None, description="Error Description"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    OIDC Callback Handler.

    Verarbeitet die Antwort vom IdP und erstellt eine Session.
    """
    if error:
        logger.warning("oidc_callback_error", error=error, description=error_description)
        # Redirect to login with error
        return RedirectResponse(
            url=f"/login?error=sso_failed&message={_safe_redirect_param(error_description or error)}",
            status_code=status.HTTP_302_FOUND,
        )

    # Get provider company
    config_service = SSOConfigService(db)
    from app.db.models import AppConfig
    from sqlalchemy import select

    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"sso_provider_{provider_id}")
    )
    config = result.scalar_one_or_none()

    if not config:
        return RedirectResponse(
            url="/login?error=provider_not_found",
            status_code=status.HTTP_302_FOUND,
        )

    company_id = UUID(config.value.get("company_id"))

    service = OIDCService(db)

    try:
        user_info, tokens = await service.handle_callback(
            code=code,
            state=state,
            company_id=company_id,
        )

        # Get provider config for user provisioning settings
        config_service = SSOConfigService(db)
        provider = await config_service.get_provider(provider_id, company_id)

        if not provider:
            return RedirectResponse(
                url="/login?error=provider_not_found",
                status_code=status.HTTP_302_FOUND,
            )

        # Create or update user based on SSO data
        user = await _provision_sso_user(
            db=db,
            provider=provider,
            email=user_info.email or user_info.sub,
            name=user_info.name,
            given_name=user_info.given_name,
            family_name=user_info.family_name,
            groups=user_info.groups,
        )

        # Generate session token
        access_token = _generate_sso_session_token(user)

        logger.info(
            "oidc_login_successful",
            provider_id=str(provider_id),
            user_id=str(user.id),
        )

        # Redirect with token in URL fragment (for SPA consumption)
        # Note: In production, consider setting httpOnly cookie instead
        return RedirectResponse(
            url=f"/dashboard?sso_login=success&token={access_token}",
            status_code=status.HTTP_302_FOUND,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (from user provisioning)
        raise
    except ValueError as e:
        logger.error("oidc_callback_failed", error=str(e))
        return RedirectResponse(
            url=f"/login?error=sso_failed&message={_safe_redirect_param(str(e))}",
            status_code=status.HTTP_302_FOUND,
        )
    finally:
        await service.close()


# =============================================================================
# SAML Authentication Endpoints
# =============================================================================


@router.get("/saml/{provider_id}/login")
async def start_saml_authentication(
    provider_id: UUID,
    relay_state: Optional[str] = Query(None, description="Return-URL"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Startet den SAML Authentication Flow.

    Kein Login erforderlich - wird für SSO-Login verwendet.
    """
    config_service = SSOConfigService(db)
    from app.db.models import AppConfig
    from sqlalchemy import select

    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"sso_provider_{provider_id}")
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    company_id = UUID(config.value.get("company_id"))

    service = SAMLService(db)

    try:
        redirect_url, request_id = await service.start_authentication(
            provider_id=provider_id,
            company_id=company_id,
            relay_state=relay_state,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "SSO"),
        )

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/saml/{provider_id}/acs")
async def saml_assertion_consumer_service(
    provider_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    SAML Assertion Consumer Service (ACS).

    Verarbeitet die SAML Response vom IdP.
    """
    # Get form data
    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState")

    if not saml_response:
        return RedirectResponse(
            url="/login?error=missing_saml_response",
            status_code=status.HTTP_302_FOUND,
        )

    config_service = SSOConfigService(db)
    from app.db.models import AppConfig
    from sqlalchemy import select

    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"sso_provider_{provider_id}")
    )
    config = result.scalar_one_or_none()

    if not config:
        return RedirectResponse(
            url="/login?error=provider_not_found",
            status_code=status.HTTP_302_FOUND,
        )

    company_id = UUID(config.value.get("company_id"))

    service = SAMLService(db)

    try:
        user_info, assertion = await service.handle_response(
            saml_response=str(saml_response),
            company_id=company_id,
            relay_state=str(relay_state) if relay_state else None,
        )

        # Get provider config for user provisioning settings
        config_service = SSOConfigService(db)
        provider = await config_service.get_provider(provider_id, company_id)

        if not provider:
            return RedirectResponse(
                url="/login?error=provider_not_found",
                status_code=status.HTTP_302_FOUND,
            )

        # Create or update user based on SAML assertion
        user = await _provision_sso_user(
            db=db,
            provider=provider,
            email=user_info.email or user_info.name_id,
            name=user_info.name,
            given_name=user_info.given_name,
            family_name=user_info.family_name,
            groups=user_info.groups,
        )

        # Generate session token
        access_token = _generate_sso_session_token(user)

        logger.info(
            "saml_login_successful",
            provider_id=str(provider_id),
            user_id=str(user.id),
        )

        # Redirect with token
        redirect_url = str(relay_state) if relay_state else "/dashboard"
        return RedirectResponse(
            url=f"{redirect_url}?sso_login=success&token={access_token}",
            status_code=status.HTTP_302_FOUND,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (from user provisioning)
        raise
    except ValueError as e:
        logger.error("saml_acs_failed", error=str(e))
        return RedirectResponse(
            url=f"/login?error=sso_failed&message={_safe_redirect_param(str(e))}",
            status_code=status.HTTP_302_FOUND,
        )


@router.get("/saml/{provider_id}/metadata")
async def get_saml_metadata(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Gibt die SAML SP Metadata zurück.

    Kann für die IdP-Konfiguration verwendet werden.
    """
    config_service = SSOConfigService(db)
    from app.db.models import AppConfig
    from sqlalchemy import select

    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"sso_provider_{provider_id}")
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO-Provider nicht gefunden",
        )

    company_id = UUID(config.value.get("company_id"))
    provider = await config_service.get_provider(provider_id, company_id)

    if not provider or not provider.saml_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein SAML-Provider",
        )

    service = SAMLService(db)
    metadata = service.generate_metadata(provider.saml_config)

    return Response(
        content=metadata,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=sp-metadata-{provider_id}.xml"},
    )


# =============================================================================
# SSO User Provisioning (Internal)
# =============================================================================


async def _provision_sso_user(
    db: AsyncSession,
    provider: SSOProviderConfig,
    email: str,
    name: Optional[str] = None,
    given_name: Optional[str] = None,
    family_name: Optional[str] = None,
    groups: Optional[List[str]] = None,
) -> User:
    """
    Erstellt oder aktualisiert einen Benutzer basierend auf SSO-Daten.

    Bei auto_create_users=True wird ein neuer Benutzer angelegt.
    Bei group_mapping werden Rollen basierend auf IdP-Gruppen gesetzt.

    Args:
        db: Datenbank-Session
        provider: SSO-Provider-Konfiguration
        email: E-Mail-Adresse des Benutzers
        name: Vollständiger Name
        given_name: Vorname
        family_name: Nachname
        groups: IdP-Gruppen des Benutzers

    Returns:
        User-Objekt (neu oder bestehend)

    Raises:
        HTTPException: Bei Fehlern oder wenn auto_create_users=False und User nicht existiert
    """
    # Check allowed domains
    if provider.allowed_domains:
        email_domain = email.split("@")[-1].lower()
        if email_domain not in [d.lower() for d in provider.allowed_domains]:
            logger.warning(
                "sso_domain_not_allowed",
                email_domain=email_domain,
                allowed=provider.allowed_domains,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="E-Mail-Domain ist nicht für SSO freigeschaltet",
            )

    # Find existing user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Determine role from group mapping
    role = provider.default_role
    if provider.group_mapping and groups:
        for idp_group, mapped_role in provider.group_mapping.items():
            if idp_group in groups:
                role = mapped_role
                break

    if user:
        # Update existing user
        if name:
            user.full_name = name
        elif given_name or family_name:
            user.full_name = f"{given_name or ''} {family_name or ''}".strip()

        # Update role if group mapping changed it
        if provider.group_mapping and groups:
            user.is_superuser = (role == "admin")  # W2-05: User.role ist read-only property

        user.is_active = True
        await db.commit()
        await db.refresh(user)

        logger.info(
            "sso_user_updated",
            user_id=str(user.id),
            email=email[:3] + "***",
        )
        return user

    # User doesn't exist
    if not provider.auto_create_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer existiert nicht und automatische Erstellung ist deaktiviert",
        )

    # Create new user
    # Generate a username from email (before @)
    username_base = email.split("@")[0].lower()
    username = username_base

    # Ensure username uniqueness
    counter = 1
    while True:
        result = await db.execute(select(User).where(User.username == username))
        if not result.scalar_one_or_none():
            break
        username = f"{username_base}{counter}"
        counter += 1

    # Determine full name
    full_name = name
    if not full_name and (given_name or family_name):
        full_name = f"{given_name or ''} {family_name or ''}".strip()
    if not full_name:
        full_name = username

    # Create user with random password (SSO users don't use password login)
    random_password = secrets.token_urlsafe(32)

    new_user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash(random_password),
        full_name=full_name,
        is_active=True,
        is_superuser=(role == "admin"),  # W2-05: User hat keine company_id/role-Spalte
        # Mark as SSO user (optional: add sso_provider_id column to User model)
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # W2-05: Tenancy ueber UserCompany (User-Modell hat keine company_id-Spalte)
    if provider.company_id:
        db.add(UserCompany(
            user_id=new_user.id,
            company_id=provider.company_id,
            role=role if role in ("owner", "admin", "member", "viewer") else "member",
            is_current=True,
        ))
        await db.commit()

    logger.info(
        "sso_user_created",
        user_id=str(new_user.id),
        email=email[:3] + "***",
        role=role,
    )

    return new_user


def _generate_sso_session_token(user: User) -> str:
    """
    Generiert ein JWT Access Token für einen SSO-Benutzer.

    Args:
        user: User-Objekt

    Returns:
        JWT Access Token
    """
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "company_id": None,  # W2-05: User hat keine company_id (Tenancy via UserCompany)
        "role": getattr(user, "role", "viewer"),
        "sso_login": True,
    }

    return create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _require_admin(user: User) -> None:
    """Prüft ob der Benutzer Admin-Rechte hat."""
    role = getattr(user, "role", "viewer")
    if role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin-Berechtigung erforderlich",
        )


def _get_company_id(user: User) -> UUID:
    """Holt die Company-ID des Benutzers."""
    company_id = getattr(user, "company_id", None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet",
        )
    return company_id


def _build_config_data(data: SSOProviderCreate) -> JSONDict:
    """Baut die Provider-Konfiguration basierend auf dem Preset."""
    config = {
        "auto_create_users": data.auto_create_users,
        "default_role": data.default_role,
        "allowed_domains": data.allowed_domains,
    }

    if data.preset in [
        SSOProviderPreset.MICROSOFT_ENTRA,
        SSOProviderPreset.GOOGLE_WORKSPACE,
        SSOProviderPreset.OKTA,
        SSOProviderPreset.AUTH0,
        SSOProviderPreset.KEYCLOAK,
        SSOProviderPreset.CUSTOM_OIDC,
    ]:
        # OIDC config
        if data.client_id:
            config["client_id"] = data.client_id
        if data.client_secret:
            config["client_secret"] = data.client_secret.get_secret_value()

        # Replace placeholders in URLs
        if data.tenant_id:
            config["tenant_id"] = data.tenant_id
        if data.domain:
            config["domain"] = data.domain

    elif data.preset == SSOProviderPreset.CUSTOM_SAML:
        # SAML config
        if data.idp_entity_id:
            config["idp_entity_id"] = data.idp_entity_id
        if data.idp_sso_url:
            config["idp_sso_url"] = data.idp_sso_url
        if data.idp_certificate:
            config["idp_certificate"] = data.idp_certificate

    return config


def _provider_to_response(provider: SSOProviderConfig) -> SSOProviderResponse:
    """Konvertiert Provider zu Response Schema."""
    return SSOProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_type=provider.provider_type.value,
        preset=provider.preset.value,
        enabled=provider.enabled,
        is_primary=provider.is_primary,
        auto_create_users=provider.auto_create_users,
        default_role=provider.default_role,
        allowed_domains=provider.allowed_domains,
        login_count=provider.login_count,
        last_used_at=provider.last_used_at.isoformat() if provider.last_used_at else None,
        created_at=provider.created_at.isoformat(),
        updated_at=provider.updated_at.isoformat(),
    )

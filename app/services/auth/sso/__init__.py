"""
SSO (Single Sign-On) Integration Services.

Enterprise-Level SSO-Unterstuetzung:
- OIDC (OpenID Connect) fuer moderne IdPs
- SAML 2.0 fuer Enterprise IdPs
- Provider-Konfiguration und Management
- Redis-basiertes State Management fuer Multi-Worker-Skalierbarkeit

Unterstuetzte Provider:
- Microsoft Entra ID (Azure AD)
- Google Workspace
- Okta
- OneLogin
- Generic SAML 2.0 / OIDC

Feinpoliert und durchdacht - Enterprise SSO auf hoechstem Niveau.
"""

from app.services.auth.sso.oidc_service import OIDCService
from app.services.auth.sso.saml_service import SAMLService
from app.services.auth.sso.sso_config_service import SSOConfigService
from app.services.auth.sso.sso_state_manager import (
    SSOStateManager,
    get_sso_state_manager,
    cleanup_sso_states,
    STATE_TTL_SECONDS,
)

__all__ = [
    "OIDCService",
    "SAMLService",
    "SSOConfigService",
    "SSOStateManager",
    "get_sso_state_manager",
    "cleanup_sso_states",
    "STATE_TTL_SECONDS",
]

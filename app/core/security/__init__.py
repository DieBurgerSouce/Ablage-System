"""Security Module.

Provides secure alternatives to dangerous operations:
- SafeExpressionEvaluator: AST-based expression evaluation (replaces eval())
- SafeModuleLoader: Whitelisted module/function loading
- SensitiveDataFilter: PII masking in logs
- SafeAttributeAccess: Controlled model attribute updates
- CertificateAuthority: Internal CA for mTLS certificates
- MTLSService: Service-to-service mTLS authentication

Also re-exports authentication functions from security_auth.py for backwards compatibility.
"""

from app.core.security.safe_expression_evaluator import SafeExpressionEvaluator
from app.core.security.safe_module_loader import SafeModuleLoader, safe_load_function
from app.core.security.sensitive_data_filter import sensitive_data_filter, mask_pii
from app.core.security.safe_attribute_access import safe_update, SafeAttributeAccess

# mTLS / Certificate Authority
from app.core.security.certificate_authority import (
    CertificateAuthority,
    CertificateInfo,
    CertificateRequest,
    CertificateType,
    KeyAlgorithm,
    CertificateAuthorityError,
    get_certificate_authority,
    ALLOWED_SERVICE_TYPES,
    SERVICE_CERT_VALIDITY_DAYS,
    SPIFFE_TRUST_DOMAIN,
)
from app.core.security.mtls_service import (
    MTLSService,
    MTLSAuthMiddleware,
    MTLSAuthResult,
    ServiceIdentity,
    ServiceCertificate,
    get_mtls_service,
    get_service_identity,
    require_service_type,
)

# Re-export auth functions from security_auth.py for backwards compatibility
from app.core.security_auth import (
    # Password handling
    verify_password,
    get_password_hash,
    validate_password_strength,
    # Token creation
    create_access_token,
    create_refresh_token,
    create_token_pair,
    create_2fa_temp_token,
    # Token verification
    decode_token,
    verify_token_type,
    verify_2fa_temp_token,
    extract_user_id_from_token,
    # Token blacklisting
    blacklist_token,
    is_token_blacklisted,
    blacklist_token_redis,
    is_token_blacklisted_redis,
    get_blacklist_stats,
    # SSRF protection
    is_ip_blocked_for_ssrf,
    validate_url_for_ssrf,
    validate_url_for_ssrf_async,
    # Header security
    sanitize_filename_for_header,
    build_content_disposition,
    sanitize_email_header,
    # TOTP replay protection
    check_and_mark_totp_used,
)

__all__ = [
    # Safe operations
    "SafeExpressionEvaluator",
    "SafeModuleLoader",
    "safe_load_function",
    "sensitive_data_filter",
    "mask_pii",
    "safe_update",
    "SafeAttributeAccess",
    # Certificate Authority / mTLS
    "CertificateAuthority",
    "CertificateInfo",
    "CertificateRequest",
    "CertificateType",
    "KeyAlgorithm",
    "CertificateAuthorityError",
    "get_certificate_authority",
    "ALLOWED_SERVICE_TYPES",
    "SERVICE_CERT_VALIDITY_DAYS",
    "SPIFFE_TRUST_DOMAIN",
    "MTLSService",
    "MTLSAuthMiddleware",
    "MTLSAuthResult",
    "ServiceIdentity",
    "ServiceCertificate",
    "get_mtls_service",
    "get_service_identity",
    "require_service_type",
    # Auth functions (from security_auth.py)
    "verify_password",
    "get_password_hash",
    "validate_password_strength",
    "create_access_token",
    "create_refresh_token",
    "create_token_pair",
    "create_2fa_temp_token",
    "decode_token",
    "verify_token_type",
    "verify_2fa_temp_token",
    "extract_user_id_from_token",
    "blacklist_token",
    "is_token_blacklisted",
    "blacklist_token_redis",
    "is_token_blacklisted_redis",
    "get_blacklist_stats",
    "is_ip_blocked_for_ssrf",
    "validate_url_for_ssrf",
    "validate_url_for_ssrf_async",
    "sanitize_filename_for_header",
    "build_content_disposition",
    "sanitize_email_header",
    "check_and_mark_totp_used",
]

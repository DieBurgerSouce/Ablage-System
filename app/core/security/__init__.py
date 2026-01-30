"""Security Module.

Provides secure alternatives to dangerous operations:
- SafeExpressionEvaluator: AST-based expression evaluation (replaces eval())
- SafeModuleLoader: Whitelisted module/function loading
- SensitiveDataFilter: PII masking in logs
- SafeAttributeAccess: Controlled model attribute updates

Also re-exports authentication functions from security_auth.py for backwards compatibility.
"""

from app.core.security.safe_expression_evaluator import SafeExpressionEvaluator
from app.core.security.safe_module_loader import SafeModuleLoader, safe_load_function
from app.core.security.sensitive_data_filter import sensitive_data_filter, mask_pii
from app.core.security.safe_attribute_access import safe_update, SafeAttributeAccess

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
    decode_token_sync,
    verify_token_type,
    verify_2fa_temp_token,
    extract_user_id_from_token,
    extract_user_id_from_token_sync,
    # Token blacklisting
    blacklist_token,
    blacklist_token_sync,
    is_token_blacklisted,
    is_token_blacklisted_sync,
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
    check_totp_replay,
    mark_totp_used,
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
    # Auth functions (from security_auth.py)
    "verify_password",
    "get_password_hash",
    "validate_password_strength",
    "create_access_token",
    "create_refresh_token",
    "create_token_pair",
    "create_2fa_temp_token",
    "decode_token",
    "decode_token_sync",
    "verify_token_type",
    "verify_2fa_temp_token",
    "extract_user_id_from_token",
    "extract_user_id_from_token_sync",
    "blacklist_token",
    "blacklist_token_sync",
    "is_token_blacklisted",
    "is_token_blacklisted_sync",
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
    "check_totp_replay",
    "mark_totp_used",
]

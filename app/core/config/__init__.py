"""
Configuration module for Ablage-System.

This module provides a modular configuration structure:
- validation.py: Security helper functions (entropy validation)
- vault_client.py: HashiCorp Vault integration
- settings (from parent config.py): Main Settings class

Usage:
    from app.core.config import settings, Settings, VaultClient
    from app.core.config.validation import validate_secret_entropy

For backwards compatibility, the main Settings class remains in
app/core/config.py and is re-exported here.

Feinpoliert und durchdacht - Modulare Konfiguration.
"""

# Re-export validation functions
from app.core.config.validation import (
    calculate_entropy_bits,
    validate_secret_entropy,
    WEAK_PASSWORDS,
    MINIO_DEFAULT_USERS,
    MINIO_DEFAULT_PASSWORDS,
)

# Re-export Vault client
from app.core.config.vault_client import (
    VaultClient,
    VAULT_AVAILABLE,
)

# Re-export Settings from parent module (backwards compatibility)
# Import from the actual config.py file using relative import trick
import importlib.util
import os

_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
_spec = importlib.util.spec_from_file_location("_config_module", _config_path)
_config_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_config_module)

# Re-export settings and Settings from config.py
settings = _config_module.settings
Settings = _config_module.Settings

__all__ = [
    # Settings
    "settings",
    "Settings",
    # Validation
    "calculate_entropy_bits",
    "validate_secret_entropy",
    "WEAK_PASSWORDS",
    "MINIO_DEFAULT_USERS",
    "MINIO_DEFAULT_PASSWORDS",
    # Vault
    "VaultClient",
    "VAULT_AVAILABLE",
]

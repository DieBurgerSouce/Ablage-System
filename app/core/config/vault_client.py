"""
HashiCorp Vault client for secure secrets management.

Supports:
- Token-based authentication
- AppRole authentication
- Kubernetes authentication
- Secret caching with TTL

Feinpoliert und durchdacht - Enterprise Secrets Management.
"""

import os
import time
from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Try to import hvac for Vault integration
try:
    import hvac
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    hvac = None  # type: ignore
    logger.debug("vault_client_not_available", message="hvac not installed, Vault integration disabled")


class VaultClient:
    """
    HashiCorp Vault client for secure secrets management.

    Supports:
    - Token-based authentication
    - AppRole authentication
    - Kubernetes authentication
    - Secret caching with TTL
    """

    _instance: Optional["VaultClient"] = None

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        vault_role_id: Optional[str] = None,
        vault_secret_id: Optional[str] = None,
        vault_namespace: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        """
        Initialize Vault client.

        Args:
            vault_addr: Vault server address
            vault_token: Vault token for authentication
            vault_role_id: AppRole role ID
            vault_secret_id: AppRole secret ID
            vault_namespace: Vault namespace (Enterprise)
            verify_ssl: Verify SSL certificates
        """
        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR", "")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN", "")
        self.vault_role_id = vault_role_id or os.getenv("VAULT_ROLE_ID", "")
        self.vault_secret_id = vault_secret_id or os.getenv("VAULT_SECRET_ID", "")
        self.vault_namespace = vault_namespace or os.getenv("VAULT_NAMESPACE", "")
        self.verify_ssl = verify_ssl

        self._client: Optional["hvac.Client"] = None
        # SECURITY FIX: Cache mit TTL-Tracking (Tuple: data, timestamp)
        self._secret_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._cache_ttl_seconds: int = 300  # 5 Minuten - rotierte Secrets werden nachgeladen
        self._authenticated = False

    @classmethod
    def get_instance(cls) -> "VaultClient":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_configured(self) -> bool:
        """Check if Vault is configured."""
        return bool(self.vault_addr and (self.vault_token or (self.vault_role_id and self.vault_secret_id)))

    def connect(self) -> bool:
        """
        Connect to Vault and authenticate.

        Returns:
            True if connection successful
        """
        if not VAULT_AVAILABLE:
            logger.warning("vault_connect_failed", reason="hvac not installed")
            return False

        if not self.is_configured():
            logger.debug("vault_not_configured", message="Vault nicht konfiguriert")
            return False

        try:
            self._client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token if self.vault_token else None,
                namespace=self.vault_namespace if self.vault_namespace else None,
                verify=self.verify_ssl,
            )

            # If no token, authenticate with AppRole
            if not self.vault_token and self.vault_role_id:
                self._authenticate_approle()

            # Verify authentication
            if self._client.is_authenticated():
                self._authenticated = True
                logger.info("vault_connected", address=self.vault_addr)
                return True
            else:
                logger.warning("vault_authentication_failed")
                return False

        except Exception as e:
            logger.error("vault_connection_error", error=str(e))
            return False

    def _authenticate_approle(self) -> None:
        """Authenticate using AppRole."""
        if self._client is None:
            raise RuntimeError("Client not initialized")
        try:
            response = self._client.auth.approle.login(
                role_id=self.vault_role_id,
                secret_id=self.vault_secret_id,
            )
            self._client.token = response["auth"]["client_token"]
            logger.info("vault_approle_authenticated")
        except Exception as e:
            logger.error("vault_approle_auth_failed", error=str(e))
            raise

    def get_secret(
        self,
        path: str,
        key: Optional[str] = None,
        mount_point: str = "secret",
        use_cache: bool = True,
    ) -> Optional[Any]:
        """
        Get secret from Vault.

        Args:
            path: Secret path in Vault
            key: Specific key within the secret (optional)
            mount_point: Vault mount point
            use_cache: Use cached value if available

        Returns:
            Secret value or None
        """
        if not self._authenticated:
            if not self.connect():
                return None

        if self._client is None:
            return None

        cache_key = f"{mount_point}/{path}"

        # SECURITY FIX: Check cache mit TTL-Pruefung
        if use_cache and cache_key in self._secret_cache:
            cached_data, cached_time = self._secret_cache[cache_key]
            # Pruefe ob Cache noch gueltig ist
            if (time.time() - cached_time) < self._cache_ttl_seconds:
                if key:
                    return cached_data.get("data", {}).get("data", {}).get(key)
                return cached_data.get("data", {}).get("data", {})
            else:
                # Cache abgelaufen - entfernen
                del self._secret_cache[cache_key]
                logger.debug("vault_cache_expired", path=path)

        try:
            # Read secret (KV v2)
            response = self._client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=mount_point,
            )

            # SECURITY FIX: Cache mit Timestamp speichern
            self._secret_cache[cache_key] = (response, time.time())

            if key:
                return response.get("data", {}).get("data", {}).get(key)
            return response.get("data", {}).get("data", {})

        except Exception as e:
            logger.warning("vault_secret_read_failed", path=path, error=str(e))
            return None

    def clear_cache(self) -> None:
        """Clear secret cache."""
        self._secret_cache.clear()
        logger.debug("vault_cache_cleared")

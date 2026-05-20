"""
Vault Client - Ablage-System OCR
Python client for HashiCorp Vault integration

Hardened: TTL-based caching, AppRole auth, retry with backoff.
Phase 1.2 - Security Haertung.
"""

import os
import time
from typing import Optional, Dict, Any, Tuple, List

import hvac
from hvac.exceptions import VaultError, InvalidPath
import structlog

logger = structlog.get_logger(__name__)

# Default TTL in seconds for the secret cache (matches VAULT_SECRET_REFRESH_INTERVAL)
_DEFAULT_CACHE_TTL: int = int(os.getenv("VAULT_SECRET_REFRESH_INTERVAL", "300"))

# Retry configuration
_RETRY_ATTEMPTS: int = 3
_RETRY_BACKOFF_SECONDS: List[int] = [1, 2, 4]


class VaultClient:
    """
    HashiCorp Vault client for secrets management.

    Hardened with:
    - TTL-based secret caching (no lru_cache forever)
    - AppRole auth with automatic token renewal
    - Retry with exponential backoff on VaultError
    - _ensure_authenticated() guard on all operations

    Usage:
        vault = VaultClient()
        secret = vault.get_secret("database/password")
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
        namespace: Optional[str] = None,
        vault_role_id: Optional[str] = None,
        vault_secret_id: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ):
        """
        Initialize Vault client.

        Args:
            url: Vault server URL (default: VAULT_ADDR env var)
            token: Vault token (default: VAULT_TOKEN env var)
            mount_point: KV secrets engine mount point
            namespace: Vault namespace (Enterprise feature)
            vault_role_id: AppRole role_id for token renewal
            vault_secret_id: AppRole secret_id for token renewal
            cache_ttl: TTL for cached secrets in seconds (default: VAULT_SECRET_REFRESH_INTERVAL or 300)
        """
        self.url = url or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self.token = token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.namespace = namespace
        self.vault_role_id = vault_role_id
        self.vault_secret_id = vault_secret_id
        self._cache_ttl: int = cache_ttl if cache_ttl is not None else _DEFAULT_CACHE_TTL

        # TTL-based secret cache: key -> (value, expiry_timestamp)
        self._secret_cache: Dict[str, Tuple[Any, float]] = {}

        if not self.token:
            raise ValueError("Vault token not provided. Set VAULT_TOKEN environment variable.")

        # Initialize hvac client
        self.client = hvac.Client(
            url=self.url,
            token=self.token,
            namespace=self.namespace,
        )

        # Verify authentication on startup
        if not self.client.is_authenticated():
            raise VaultError("Failed to authenticate with Vault")

        logger.info("vault_client_initialized", url=self.url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_authenticated(self) -> None:
        """
        Ensure the client holds a valid Vault token.

        If the current token has expired, attempt to re-authenticate via
        AppRole (if role_id/secret_id are configured) or raise VaultError.
        """
        if self.client.is_authenticated():
            return

        if self.vault_role_id and self.vault_secret_id:
            logger.warning(
                "vault_token_expired",
                message="Vault token abgelaufen - AppRole re-authentication",
            )
            try:
                response = self.client.auth.approle.login(
                    role_id=self.vault_role_id,
                    secret_id=self.vault_secret_id,
                )
                self.token = response["auth"]["client_token"]
                self.client.token = self.token
                logger.info("vault_approle_reauthenticated")
            except VaultError as e:
                logger.error(
                    "vault_approle_reauth_failed",
                    error=str(e),
                )
                raise VaultError("Vault re-authentication via AppRole fehlgeschlagen") from e
        else:
            raise VaultError(
                "Vault token abgelaufen und keine AppRole-Credentials konfiguriert"
            )

    def _retry_operation(self, operation_name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a callable with retry and exponential backoff on VaultError.

        Args:
            operation_name: Human-readable name for logging
            fn: Callable to invoke
            *args: Positional arguments forwarded to fn
            **kwargs: Keyword arguments forwarded to fn

        Returns:
            Result of fn(*args, **kwargs)

        Raises:
            VaultError: After all retry attempts are exhausted
        """
        last_exc: Optional[Exception] = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return fn(*args, **kwargs)
            except VaultError as e:
                last_exc = e
                if attempt < _RETRY_ATTEMPTS - 1:
                    backoff = _RETRY_BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "vault_operation_retry",
                        operation=operation_name,
                        attempt=attempt + 1,
                        backoff_seconds=backoff,
                        error=str(e),
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "vault_operation_exhausted",
                        operation=operation_name,
                        attempts=_RETRY_ATTEMPTS,
                        error=str(e),
                    )
        raise last_exc  # type: ignore[misc]

    def _cache_key(self, path: str, key: Optional[str]) -> str:
        """Build a cache dict key from path and optional key."""
        return f"{path}::{key}" if key else path

    def _get_from_cache(self, cache_key: str) -> Tuple[bool, Any]:
        """
        Check TTL cache for a cached secret.

        Returns:
            (hit, value) - hit=True if cached and not expired
        """
        if cache_key in self._secret_cache:
            value, expiry = self._secret_cache[cache_key]
            if time.monotonic() < expiry:
                return True, value
            # Expired: evict
            del self._secret_cache[cache_key]
        return False, None

    def _store_in_cache(self, cache_key: str, value: Any) -> None:
        """Store a value in the TTL cache with current TTL."""
        self._secret_cache[cache_key] = (value, time.monotonic() + self._cache_ttl)

    def invalidate_cache(self, path: Optional[str] = None, key: Optional[str] = None) -> None:
        """
        Invalidate the secret cache.

        Args:
            path: If provided, only invalidate entries for this path.
                  If None, clear the entire cache.
            key: If provided together with path, only that specific (path, key) entry.
        """
        if path is None:
            self._secret_cache.clear()
            return
        cache_key = self._cache_key(path, key)
        self._secret_cache.pop(cache_key, None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_secret(self, path: str, key: Optional[str] = None) -> Any:
        """
        Get secret from Vault with TTL-based caching.

        Secrets are cached for _cache_ttl seconds (default 300s / 5 min).
        The cache is invalidated on set_secret/delete_secret.

        Args:
            path: Secret path (e.g., 'ablage-system/database')
            key: Specific key to retrieve from secret (optional)

        Returns:
            Secret value or dict of all keys

        Raises:
            InvalidPath: If secret path doesn't exist
            VaultError: For other Vault errors
            KeyError: If the requested key is not in the secret
        """
        ck = self._cache_key(path, key)
        hit, cached_value = self._get_from_cache(ck)
        if hit:
            return cached_value

        self._ensure_authenticated()

        def _fetch() -> Any:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )
            data = response["data"]["data"]
            if key:
                if key not in data:
                    raise KeyError(f"Key '{key}' not found in secret '{path}'")
                return data[key]
            return data

        try:
            value = self._retry_operation("get_secret", _fetch)
            self._store_in_cache(ck, value)
            return value
        except InvalidPath:
            logger.error("secret_not_found", path=path)
            raise
        except VaultError as e:
            logger.error("vault_read_error", path=path, error=str(e))
            raise

    def set_secret(self, path: str, data: Dict[str, Any]) -> None:
        """
        Write secret to Vault.

        Args:
            path: Secret path
            data: Secret data (key-value pairs)
        """
        self._ensure_authenticated()

        def _write() -> None:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                mount_point=self.mount_point,
            )

        try:
            self._retry_operation("set_secret", _write)
            logger.info("secret_updated", path=path)
            # Invalidate all cache entries for this path
            self.invalidate_cache(path=path)
        except VaultError as e:
            logger.error("secret_write_failed", path=path, error=str(e))
            raise

    def delete_secret(self, path: str) -> None:
        """
        Delete secret from Vault.

        Args:
            path: Secret path
        """
        self._ensure_authenticated()

        def _delete() -> None:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point,
            )

        try:
            self._retry_operation("delete_secret", _delete)
            logger.info("secret_deleted", path=path)
            self.invalidate_cache(path=path)
        except VaultError as e:
            logger.error("secret_delete_failed", path=path, error=str(e))
            raise

    def list_secrets(self, path: str = "") -> List[str]:
        """
        List secrets at path.

        Args:
            path: Directory path to list

        Returns:
            List of secret names
        """
        self._ensure_authenticated()

        def _list() -> List[str]:
            response = self.client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_point,
            )
            return response["data"]["keys"]  # type: ignore[no-any-return]

        try:
            return self._retry_operation("list_secrets", _list)
        except InvalidPath:
            return []
        except VaultError as e:
            logger.error("secrets_list_failed", path=path, error=str(e))
            raise

    def get_database_credentials(self, role: str = "ablage-backend") -> Dict[str, str]:
        """
        Get dynamic database credentials from Vault.

        Args:
            role: Database role name

        Returns:
            Dictionary with username, password, lease_id, lease_duration
        """
        self._ensure_authenticated()

        def _creds() -> Dict[str, str]:
            response = self.client.secrets.database.generate_credentials(name=role)
            return {
                "username": response["data"]["username"],
                "password": response["data"]["password"],
                "lease_id": response["lease_id"],
                "lease_duration": response["lease_duration"],
            }

        try:
            return self._retry_operation("get_database_credentials", _creds)
        except VaultError as e:
            logger.error("database_credentials_generation_failed", error=str(e))
            raise

    def renew_lease(self, lease_id: str, increment: Optional[int] = None) -> None:
        """
        Renew a lease.

        Args:
            lease_id: Lease ID to renew
            increment: Lease extension in seconds
        """
        self._ensure_authenticated()

        def _renew() -> None:
            self.client.sys.renew_lease(
                lease_id=lease_id,
                increment=increment,
            )

        try:
            self._retry_operation("renew_lease", _renew)
            logger.info("lease_renewed", lease_id=lease_id)
        except VaultError as e:
            logger.error("lease_renewal_failed", lease_id=lease_id, error=str(e))
            raise

    def revoke_lease(self, lease_id: str) -> None:
        """
        Revoke a lease.

        Args:
            lease_id: Lease ID to revoke
        """
        self._ensure_authenticated()

        def _revoke() -> None:
            self.client.sys.revoke_lease(lease_id=lease_id)

        try:
            self._retry_operation("revoke_lease", _revoke)
            logger.info("lease_revoked", lease_id=lease_id)
        except VaultError as e:
            logger.error("lease_revocation_failed", lease_id=lease_id, error=str(e))
            raise


# Singleton instance
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    """
    Get singleton Vault client instance.

    Reads optional AppRole credentials from environment variables:
    - VAULT_ROLE_ID
    - VAULT_SECRET_ID

    Returns:
        VaultClient instance
    """
    global _vault_client

    if _vault_client is None:
        _vault_client = VaultClient(
            vault_role_id=os.getenv("VAULT_ROLE_ID"),
            vault_secret_id=os.getenv("VAULT_SECRET_ID"),
        )

    return _vault_client


# Convenience functions
def get_secret(path: str, key: Optional[str] = None) -> Any:
    """Get secret from Vault."""
    return get_vault_client().get_secret(path, key)


def set_secret(path: str, data: Dict[str, Any]) -> None:
    """Write secret to Vault."""
    get_vault_client().set_secret(path, data)


# Configuration loader
class VaultConfig:
    """
    Load application configuration from Vault.

    Usage:
        config = VaultConfig()
        db_password = config.database.password
    """

    def __init__(self, base_path: str = "ablage-system"):
        self.vault = get_vault_client()
        self.base_path = base_path

    def __getattr__(self, name: str) -> "VaultSecretGroup":
        """Dynamic attribute access for secrets."""
        return VaultSecretGroup(self.vault, f"{self.base_path}/{name}")


class VaultSecretGroup:
    """Represents a group of secrets at a path."""

    def __init__(self, vault: VaultClient, path: str):
        self.vault = vault
        self.path = path
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> None:
        """Lazy load secret data."""
        if self._data is None:
            self._data = self.vault.get_secret(self.path)

    def __getattr__(self, name: str) -> Any:
        """Get specific key from secret group."""
        self._load()
        if name not in self._data:  # type: ignore[operator]
            raise AttributeError(f"Secret '{self.path}' has no key '{name}'")
        return self._data[name]  # type: ignore[index]

    def __getitem__(self, key: str) -> Any:
        """Dict-style access."""
        self._load()
        return self._data[key]  # type: ignore[index]

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style get with default."""
        self._load()
        return self._data.get(key, default)  # type: ignore[union-attr]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        self._load()
        return self._data.copy()  # type: ignore[union-attr]

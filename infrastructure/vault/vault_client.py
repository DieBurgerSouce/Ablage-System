"""
Vault Client - Ablage-System OCR
Python client for HashiCorp Vault integration
"""

import os
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

import hvac
from hvac.exceptions import VaultError, InvalidPath

logger = logging.getLogger(__name__)


class VaultClient:
    """
    HashiCorp Vault client for secrets management.

    Usage:
        vault = VaultClient()
        secret = vault.get_secret("database/password")
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
        namespace: Optional[str] = None
    ):
        """
        Initialize Vault client.

        Args:
            url: Vault server URL (default: VAULT_ADDR env var)
            token: Vault token (default: VAULT_TOKEN env var)
            mount_point: KV secrets engine mount point
            namespace: Vault namespace (Enterprise feature)
        """
        self.url = url or os.getenv('VAULT_ADDR', 'http://localhost:8200')
        self.token = token or os.getenv('VAULT_TOKEN')
        self.mount_point = mount_point
        self.namespace = namespace

        if not self.token:
            raise ValueError("Vault token not provided. Set VAULT_TOKEN environment variable.")

        # Initialize hvac client
        self.client = hvac.Client(
            url=self.url,
            token=self.token,
            namespace=self.namespace
        )

        # Verify authentication
        if not self.client.is_authenticated():
            raise VaultError("Failed to authenticate with Vault")

        logger.info(f"Vault client initialized: {self.url}")

    @lru_cache(maxsize=128)
    def get_secret(self, path: str, key: Optional[str] = None) -> Any:
        """
        Get secret from Vault (cached).

        Args:
            path: Secret path (e.g., 'ablage-system/database')
            key: Specific key to retrieve from secret (optional)

        Returns:
            Secret value or dict of all keys

        Raises:
            InvalidPath: If secret path doesn't exist
            VaultError: For other Vault errors
        """
        try:
            # Read secret from KV v2
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point
            )

            data = response['data']['data']

            if key:
                if key not in data:
                    raise KeyError(f"Key '{key}' not found in secret '{path}'")
                return data[key]

            return data

        except InvalidPath:
            logger.error(f"Secret not found: {path}")
            raise
        except VaultError as e:
            logger.error(f"Vault error reading {path}: {e}")
            raise

    def set_secret(self, path: str, data: Dict[str, Any]) -> None:
        """
        Write secret to Vault.

        Args:
            path: Secret path
            data: Secret data (key-value pairs)
        """
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                mount_point=self.mount_point
            )
            logger.info(f"Secret updated: {path}")

            # Invalidate cache for this path
            self.get_secret.cache_clear()

        except VaultError as e:
            logger.error(f"Failed to write secret {path}: {e}")
            raise

    def delete_secret(self, path: str) -> None:
        """
        Delete secret from Vault.

        Args:
            path: Secret path
        """
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point=self.mount_point
            )
            logger.info(f"Secret deleted: {path}")

            # Invalidate cache
            self.get_secret.cache_clear()

        except VaultError as e:
            logger.error(f"Failed to delete secret {path}: {e}")
            raise

    def list_secrets(self, path: str = "") -> list[str]:
        """
        List secrets at path.

        Args:
            path: Directory path to list

        Returns:
            List of secret names
        """
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_point
            )
            return response['data']['keys']

        except InvalidPath:
            return []
        except VaultError as e:
            logger.error(f"Failed to list secrets at {path}: {e}")
            raise

    def get_database_credentials(self, role: str = "ablage-backend") -> Dict[str, str]:
        """
        Get dynamic database credentials from Vault.

        Args:
            role: Database role name

        Returns:
            Dictionary with username and password
        """
        try:
            response = self.client.secrets.database.generate_credentials(
                name=role
            )
            return {
                'username': response['data']['username'],
                'password': response['data']['password'],
                'lease_id': response['lease_id'],
                'lease_duration': response['lease_duration']
            }

        except VaultError as e:
            logger.error(f"Failed to generate database credentials: {e}")
            raise

    def renew_lease(self, lease_id: str, increment: Optional[int] = None) -> None:
        """
        Renew a lease.

        Args:
            lease_id: Lease ID to renew
            increment: Lease extension in seconds
        """
        try:
            self.client.sys.renew_lease(
                lease_id=lease_id,
                increment=increment
            )
            logger.info(f"Lease renewed: {lease_id}")

        except VaultError as e:
            logger.error(f"Failed to renew lease {lease_id}: {e}")
            raise

    def revoke_lease(self, lease_id: str) -> None:
        """
        Revoke a lease.

        Args:
            lease_id: Lease ID to revoke
        """
        try:
            self.client.sys.revoke_lease(lease_id=lease_id)
            logger.info(f"Lease revoked: {lease_id}")

        except VaultError as e:
            logger.error(f"Failed to revoke lease {lease_id}: {e}")
            raise


# Singleton instance
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    """
    Get singleton Vault client instance.

    Returns:
        VaultClient instance
    """
    global _vault_client

    if _vault_client is None:
        _vault_client = VaultClient()

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

    def __getattr__(self, name: str):
        """Dynamic attribute access for secrets."""
        return VaultSecretGroup(self.vault, f"{self.base_path}/{name}")


class VaultSecretGroup:
    """Represents a group of secrets at a path."""

    def __init__(self, vault: VaultClient, path: str):
        self.vault = vault
        self.path = path
        self._data = None

    def _load(self):
        """Lazy load secret data."""
        if self._data is None:
            self._data = self.vault.get_secret(self.path)

    def __getattr__(self, name: str):
        """Get specific key from secret group."""
        self._load()
        if name not in self._data:
            raise AttributeError(f"Secret '{self.path}' has no key '{name}'")
        return self._data[name]

    def __getitem__(self, key: str):
        """Dict-style access."""
        self._load()
        return self._data[key]

    def get(self, key: str, default=None):
        """Dict-style get with default."""
        self._load()
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        self._load()
        return self._data.copy()

"""
HashiCorp Vault client for secure secrets management.

Supports:
- Token-based authentication
- AppRole authentication
- Kubernetes authentication
- Secret caching with TTL
- Transit Secrets Engine (Encryption-as-a-Service)

Feinpoliert und durchdacht - Enterprise Secrets Management.

Art. 32 DSGVO - Sicherheit der Verarbeitung
Transit ermöglicht Verschlüsselung ohne lokale Schlüsselverwaltung.
"""

import base64
import os
import re
import threading
import time
from typing import Any, Dict, Optional, Tuple

import structlog

from app.core.safe_errors import safe_error_log

# Key name validation pattern (security: prevent path traversal)
_KEY_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

logger = structlog.get_logger(__name__)

# Try to import hvac for Vault integration
try:
    import hvac
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    hvac = None  # type: ignore
    logger.debug(
        "vault_client_nicht_verfügbar",
        message="hvac nicht installiert, Vault-Integration deaktiviert",
    )


class VaultClient:
    """
    HashiCorp Vault client for secure secrets management.

    Supports:
    - Token-based authentication
    - AppRole authentication
    - Kubernetes authentication
    - Secret caching with TTL
    - Transit Secrets Engine (Encryption-as-a-Service)

    Thread-safe Singleton Pattern.
    """

    _instance: Optional["VaultClient"] = None
    _lock: threading.Lock = threading.Lock()

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
        """Get thread-safe singleton instance."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_configured(self) -> bool:
        """Check if Vault is configured."""
        return bool(self.vault_addr and (self.vault_token or (self.vault_role_id and self.vault_secret_id)))

    def is_healthy(self) -> bool:
        """
        Check if Vault is healthy and connected.

        Returns:
            True if Vault is connected and authenticated
        """
        if not VAULT_AVAILABLE:
            return False

        if not self.is_configured():
            return False

        if not self._authenticated:
            return False

        if self._client is None:
            return False

        try:
            # Try to authenticate to verify connection is still valid
            return self._client.is_authenticated()
        except Exception as e:
            logger.debug("vault_health_check_failed", **safe_error_log(e))
            return False

    def connect(self) -> bool:
        """
        Connect to Vault and authenticate.

        Returns:
            True if connection successful
        """
        if not VAULT_AVAILABLE:
            logger.warning(
                "vault_verbindung_fehlgeschlagen",
                reason="hvac nicht installiert",
                message="Vault-Verbindung nicht möglich ohne hvac-Bibliothek",
            )
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
            logger.error("vault_connection_error", **safe_error_log(e))
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
            logger.error("vault_approle_auth_failed", **safe_error_log(e))
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

        # SECURITY FIX: Check cache mit TTL-Prüfung
        if use_cache and cache_key in self._secret_cache:
            cached_data, cached_time = self._secret_cache[cache_key]
            # Prüfe ob Cache noch gültig ist
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
            logger.warning("vault_secret_read_failed", path=path, **safe_error_log(e))
            return None

    def clear_cache(self) -> None:
        """Clear secret cache."""
        self._secret_cache.clear()
        logger.debug("vault_cache_cleared")

    # ========== Transit Secrets Engine ==========

    def _validate_key_name(self, key_name: str) -> bool:
        """
        Validate Transit key name to prevent path traversal attacks.

        Args:
            key_name: Key name to validate

        Returns:
            True if valid, False otherwise
        """
        if not key_name or not _KEY_NAME_PATTERN.match(key_name):
            logger.warning(
                "vault_transit_invalid_key_name",
                key_name=key_name[:64] if key_name else "None",
            )
            return False
        return True

    def transit_encrypt(
        self,
        plaintext: str,
        key_name: str = "ablage-encryption-key",
        context: Optional[str] = None,
        mount_point: str = "transit",
    ) -> Optional[str]:
        """
        Encrypt data using Vault Transit Secrets Engine.

        Provides Encryption-as-a-Service (EaaS) where:
        - Vault manages encryption keys (never leaves Vault)
        - Automatic key rotation supported
        - Audit logging of all operations

        Args:
            plaintext: Data to encrypt
            key_name: Transit key name (must exist in Vault, validated against pattern)
            context: Optional key derivation context (for convergent encryption)
            mount_point: Transit mount point

        Returns:
            Vault ciphertext (format: vault:v1:base64_ciphertext) or None on error
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return None

        if not self._authenticated:
            if not self.connect():
                return None

        if self._client is None:
            return None

        try:
            # Encode plaintext as base64 (Vault requirement)
            plaintext_b64 = base64.b64encode(plaintext.encode('utf-8')).decode('utf-8')

            # Prepare context if provided
            context_b64 = None
            if context:
                context_b64 = base64.b64encode(context.encode('utf-8')).decode('utf-8')

            # Encrypt via Transit
            response = self._client.secrets.transit.encrypt_data(
                name=key_name,
                plaintext=plaintext_b64,
                context=context_b64,
                mount_point=mount_point,
            )

            ciphertext = response.get("data", {}).get("ciphertext")
            if ciphertext:
                logger.debug(
                    "vault_transit_encrypted",
                    key_name=key_name,
                    plaintext_length=len(plaintext),
                )
                return ciphertext

            logger.warning(
                "vault_transit_encrypt_kein_ciphertext",
                key_name=key_name,
                message="Verschluesselung gab keinen Ciphertext zurück",
            )
            return None

        except Exception as e:
            logger.error(
                "vault_transit_encrypt_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Transit-Verschluesselung fehlgeschlagen",
            )
            return None

    def transit_decrypt(
        self,
        ciphertext: str,
        key_name: str = "ablage-encryption-key",
        context: Optional[str] = None,
        mount_point: str = "transit",
    ) -> Optional[str]:
        """
        Decrypt data using Vault Transit Secrets Engine.

        Args:
            ciphertext: Vault-encrypted ciphertext (format: vault:v1:base64_ciphertext)
            key_name: Transit key name (validated against pattern)
            context: Optional key derivation context (must match encryption)
            mount_point: Transit mount point

        Returns:
            Decrypted plaintext or None on error
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return None

        if not self._authenticated:
            if not self.connect():
                return None

        if self._client is None:
            return None

        try:
            # Prepare context if provided
            context_b64 = None
            if context:
                context_b64 = base64.b64encode(context.encode('utf-8')).decode('utf-8')

            # Decrypt via Transit
            response = self._client.secrets.transit.decrypt_data(
                name=key_name,
                ciphertext=ciphertext,
                context=context_b64,
                mount_point=mount_point,
            )

            plaintext_b64 = response.get("data", {}).get("plaintext")
            if plaintext_b64:
                plaintext = base64.b64decode(plaintext_b64).decode('utf-8')
                logger.debug(
                    "vault_transit_decrypted",
                    key_name=key_name,
                    plaintext_length=len(plaintext),
                )
                return plaintext

            logger.warning(
                "vault_transit_decrypt_kein_plaintext",
                key_name=key_name,
                message="Entschluesselung gab keinen Plaintext zurück",
            )
            return None

        except Exception as e:
            logger.error(
                "vault_transit_decrypt_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Transit-Entschluesselung fehlgeschlagen",
            )
            return None

    def transit_rewrap(
        self,
        ciphertext: str,
        key_name: str = "ablage-encryption-key",
        context: Optional[str] = None,
        mount_point: str = "transit",
    ) -> Optional[str]:
        """
        Re-encrypt ciphertext with latest key version (for key rotation).

        This allows upgrading encryption to the latest key version
        without exposing the plaintext.

        Args:
            ciphertext: Existing vault ciphertext
            key_name: Transit key name (validated against pattern)
            context: Optional key derivation context
            mount_point: Transit mount point

        Returns:
            Re-encrypted ciphertext with latest key version or None on error
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return None

        if not self._authenticated:
            if not self.connect():
                return None

        if self._client is None:
            return None

        try:
            context_b64 = None
            if context:
                context_b64 = base64.b64encode(context.encode('utf-8')).decode('utf-8')

            response = self._client.secrets.transit.rewrap_data(
                name=key_name,
                ciphertext=ciphertext,
                context=context_b64,
                mount_point=mount_point,
            )

            new_ciphertext = response.get("data", {}).get("ciphertext")
            if new_ciphertext:
                logger.info(
                    "vault_transit_rewrapped",
                    key_name=key_name,
                    message="Ciphertext mit neuer Key-Version verschluesselt",
                )
                return new_ciphertext

            logger.warning(
                "vault_transit_rewrap_kein_ciphertext",
                key_name=key_name,
                message="Rewrap gab keinen neuen Ciphertext zurück",
            )
            return None

        except Exception as e:
            logger.error(
                "vault_transit_rewrap_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Transit-Rewrap fehlgeschlagen",
            )
            return None

    def transit_create_key(
        self,
        key_name: str,
        key_type: str = "aes256-gcm96",
        exportable: bool = False,
        allow_plaintext_backup: bool = False,
        mount_point: str = "transit",
    ) -> bool:
        """
        Create a new Transit encryption key.

        Args:
            key_name: Name for the new key (validated against pattern)
            key_type: Key type (aes256-gcm96, chacha20-poly1305, etc.)
            exportable: Whether key can be exported (security risk if True)
            allow_plaintext_backup: Allow plaintext backup (security risk if True)
            mount_point: Transit mount point

        Returns:
            True if key created successfully
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return False

        if not self._authenticated:
            if not self.connect():
                return False

        if self._client is None:
            return False

        try:
            self._client.secrets.transit.create_key(
                name=key_name,
                key_type=key_type,
                exportable=exportable,
                allow_plaintext_backup=allow_plaintext_backup,
                mount_point=mount_point,
            )

            logger.info(
                "vault_transit_key_erstellt",
                key_name=key_name,
                key_type=key_type,
                message="Neuer Transit-Key wurde erstellt",
            )
            return True

        except Exception as e:
            # Key might already exist
            if "already exists" in str(e).lower():
                logger.debug(
                    "vault_transit_key_existiert",
                    key_name=key_name,
                    message="Key existiert bereits",
                )
                return True

            logger.error(
                "vault_transit_key_erstellen_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Transit-Key konnte nicht erstellt werden",
            )
            return False

    def transit_rotate_key(
        self,
        key_name: str,
        mount_point: str = "transit",
    ) -> bool:
        """
        Rotate a Transit encryption key to a new version.

        Existing data can still be decrypted with old versions.
        Use rewrap to upgrade ciphertext to new key version.

        Args:
            key_name: Key to rotate (validated against pattern)
            mount_point: Transit mount point

        Returns:
            True if rotation successful
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return False

        if not self._authenticated:
            if not self.connect():
                return False

        if self._client is None:
            return False

        try:
            self._client.secrets.transit.rotate_key(
                name=key_name,
                mount_point=mount_point,
            )

            logger.info(
                "vault_transit_key_rotiert",
                key_name=key_name,
                message="Transit-Key wurde auf neue Version rotiert",
            )
            return True

        except Exception as e:
            logger.error(
                "vault_transit_key_rotation_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Key-Rotation fehlgeschlagen",
            )
            return False

    def transit_get_key_info(
        self,
        key_name: str,
        mount_point: str = "transit",
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a Transit key.

        Args:
            key_name: Key to get info for (validated against pattern)
            mount_point: Transit mount point

        Returns:
            Key info dict with versions, type, etc. or None on error
        """
        # Security: Validate key name
        if not self._validate_key_name(key_name):
            return None

        if not self._authenticated:
            if not self.connect():
                return None

        if self._client is None:
            return None

        try:
            response = self._client.secrets.transit.read_key(
                name=key_name,
                mount_point=mount_point,
            )

            return response.get("data", {})

        except Exception as e:
            logger.warning(
                "vault_transit_key_info_fehlgeschlagen",
                key_name=key_name,
                **safe_error_log(e),
                message="Key-Info konnte nicht abgerufen werden",
            )
            return None


# ========== Vault Transit Encryption Service ==========

class VaultTransitEncryptionService:
    """
    High-level encryption service using Vault Transit.

    Provides a clean API for encrypting/decrypting data using
    HashiCorp Vault's Transit Secrets Engine with automatic fallback
    to local AES encryption when Vault is not available.

    Thread-safe Singleton Pattern.
    Feinpoliert und durchdacht - Enterprise Encryption-as-a-Service.

    Art. 32 DSGVO - Sicherheit der Verarbeitung
    """

    _instance: Optional["VaultTransitEncryptionService"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        vault_client: Optional[VaultClient] = None,
        key_name: str = "ablage-encryption-key",
        mount_point: str = "transit",
        fallback_to_local: bool = True,
    ):
        """
        Initialize Vault Transit Encryption Service.

        Args:
            vault_client: Optional VaultClient instance
            key_name: Default Transit key name
            mount_point: Transit mount point
            fallback_to_local: If True, fallback to local encryption when Vault unavailable
        """
        self.vault_client = vault_client or VaultClient.get_instance()
        self.key_name = key_name
        self.mount_point = mount_point
        self.fallback_to_local = fallback_to_local
        self._vault_available: Optional[bool] = None

    @classmethod
    def get_instance(cls) -> "VaultTransitEncryptionService":
        """Get thread-safe singleton instance."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_vault_available(self) -> bool:
        """Check if Vault Transit is available and usable."""
        if self._vault_available is not None:
            return self._vault_available

        # Try to connect and verify Transit is usable
        if not self.vault_client.is_configured():
            self._vault_available = False
            return False

        if not self.vault_client.connect():
            self._vault_available = False
            return False

        # Try to create or verify key exists
        self._vault_available = self.vault_client.transit_create_key(
            key_name=self.key_name,
            mount_point=self.mount_point,
        )

        return self._vault_available

    def encrypt(
        self,
        plaintext: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Encrypt data using Vault Transit (or local fallback).

        Args:
            plaintext: Data to encrypt
            context: Optional context for key derivation (e.g., user_id)

        Returns:
            Encrypted ciphertext (prefixed with vault: or local:)

        Raises:
            EncryptionError: If encryption fails and no fallback
        """
        # Try Vault Transit first
        if self.is_vault_available():
            ciphertext = self.vault_client.transit_encrypt(
                plaintext=plaintext,
                key_name=self.key_name,
                context=context,
                mount_point=self.mount_point,
            )
            if ciphertext:
                # Prefix with transit: to identify backend
                return f"transit:{ciphertext}"

            logger.warning(
                "vault_transit_encrypt_fehlgeschlagen_fallback",
                message="Vault Transit fehlgeschlagen, versuche lokale Verschluesselung",
            )

        # Fallback to local encryption
        if self.fallback_to_local:
            # NOTE: Import hier um zirkuläre Imports zu vermeiden
            # (encryption.py importiert evtl. config-Module)
            from app.core.encryption import encrypt_data
            local_ciphertext = encrypt_data(plaintext, associated_data=context)
            return f"local:{local_ciphertext}"

        raise VaultTransitError(
            "Vault Transit nicht verfügbar und kein Fallback aktiviert",
        )

    def decrypt(
        self,
        ciphertext: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Decrypt data (auto-detects backend from prefix).

        Args:
            ciphertext: Encrypted data (with transit: or local: prefix)
            context: Optional context for key derivation

        Returns:
            Decrypted plaintext

        Raises:
            DecryptionError: If decryption fails
        """
        # Detect backend from prefix
        if ciphertext.startswith("transit:"):
            vault_ciphertext = ciphertext[8:]  # Remove "transit:" prefix
            if self.is_vault_available():
                plaintext = self.vault_client.transit_decrypt(
                    ciphertext=vault_ciphertext,
                    key_name=self.key_name,
                    context=context,
                    mount_point=self.mount_point,
                )
                if plaintext is not None:
                    return plaintext

            raise VaultTransitError(
                "Vault Transit nicht verfügbar für Entschluesselung",
            )

        elif ciphertext.startswith("local:"):
            local_ciphertext = ciphertext[6:]  # Remove "local:" prefix
            # NOTE: Import hier um zirkuläre Imports zu vermeiden
            from app.core.encryption import decrypt_data
            return decrypt_data(local_ciphertext, associated_data=context)

        else:
            # Legacy format - assume local encryption
            # NOTE: Import hier um zirkuläre Imports zu vermeiden
            from app.core.encryption import decrypt_data

            return decrypt_data(ciphertext, associated_data=context)

    def rewrap(
        self,
        ciphertext: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Re-encrypt with latest key version (Vault Transit only).

        For local encryption, this re-encrypts the data.

        Args:
            ciphertext: Existing encrypted data
            context: Optional context for key derivation

        Returns:
            Re-encrypted ciphertext with latest key
        """
        if ciphertext.startswith("transit:"):
            if self.is_vault_available():
                vault_ciphertext = ciphertext[8:]
                new_ciphertext = self.vault_client.transit_rewrap(
                    ciphertext=vault_ciphertext,
                    key_name=self.key_name,
                    context=context,
                    mount_point=self.mount_point,
                )
                if new_ciphertext:
                    return f"transit:{new_ciphertext}"

            raise VaultTransitError("Vault Transit nicht verfügbar für Rewrap")

        # For local encryption, decrypt and re-encrypt
        plaintext = self.decrypt(ciphertext, context)
        return self.encrypt(plaintext, context)

    def migrate_to_vault(
        self,
        ciphertext: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Migrate local-encrypted data to Vault Transit.

        Args:
            ciphertext: Local-encrypted data
            context: Optional context for key derivation

        Returns:
            Vault Transit encrypted ciphertext
        """
        if ciphertext.startswith("transit:"):
            # Already using Vault Transit
            return ciphertext

        if not self.is_vault_available():
            raise VaultTransitError(
                "Vault Transit nicht verfügbar für Migration",
            )

        # Decrypt local
        plaintext = self.decrypt(ciphertext, context)

        # Re-encrypt with Vault Transit
        vault_ciphertext = self.vault_client.transit_encrypt(
            plaintext=plaintext,
            key_name=self.key_name,
            context=context,
            mount_point=self.mount_point,
        )

        if vault_ciphertext:
            logger.info(
                "daten_zu_vault_transit_migriert",
                message="Lokale Verschluesselung erfolgreich zu Vault Transit migriert",
            )
            return f"transit:{vault_ciphertext}"

        raise VaultTransitError("Migration zu Vault Transit fehlgeschlagen")


class VaultTransitError(Exception):
    """Vault Transit operation error."""

    def __init__(self, message: str):
        self.message = message
        self.user_message_de = message  # Already German
        super().__init__(message)

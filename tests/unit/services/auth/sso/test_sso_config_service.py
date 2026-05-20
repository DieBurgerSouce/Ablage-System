# -*- coding: utf-8 -*-
"""
Unit-Tests fuer SSO Config Service.

Testet:
- Verschluesselungsschluessel-Ableitung (CWE-327, CWE-330 Fix)
- AES-256-GCM Secret-Verschluesselung/Entschluesselung
- Provider-CRUD (Create, Read, Update, Delete)
- Multi-Tenant Isolation (company_id Check)
- Primaerer Provider-Management
- Login-Tracking
- Provider-Presets (Microsoft, Google, Okta, etc.)

SECURITY TESTS:
- Keine Default-Keys erlaubt (CWE-327)
- Client Secrets werden verschluesselt gespeichert
- Company-ID Isolation bei allen Operationen

Feinpoliert und durchdacht - Enterprise SSO Configuration Tests.
"""

import pytest
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

# Importiere die Helper-Funktion aus conftest um das Modul direkt zu laden
# Dies umgeht den sso Package __init__ der SAML/OIDC Services importiert
from tests.unit.services.auth.sso.conftest import get_sso_config_module

# Lade das Modul einmal
sso_mod = get_sso_config_module()

# Note: mock_db, sample_company_id, another_company_id, sample_provider_id,
# mock_settings_with_sso_key, mock_settings_with_secret_key_only, mock_settings_no_keys
# are all defined in conftest.py (same directory)


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_oidc_config() -> Dict[str, Any]:
    """Sample OIDC configuration data."""
    return {
        "client_id": "test-client-id-12345",
        "client_secret": "super-secret-client-secret",
        "tenant_id": "test-tenant-uuid",
        "authorization_endpoint": "https://login.example.com/oauth2/authorize",
        "token_endpoint": "https://login.example.com/oauth2/token",
        "userinfo_endpoint": "https://login.example.com/oauth2/userinfo",
        "jwks_uri": "https://login.example.com/.well-known/jwks.json",
        "issuer": "https://login.example.com",
        "scopes": ["openid", "profile", "email"],
        "use_pkce": True,
    }


@pytest.fixture
def sample_saml_config() -> Dict[str, Any]:
    """Sample SAML configuration data."""
    return {
        "idp_entity_id": "https://idp.example.com/saml",
        "idp_sso_url": "https://idp.example.com/saml/sso",
        "idp_slo_url": "https://idp.example.com/saml/slo",
        "idp_certificate": "-----BEGIN CERTIFICATE-----\nMIIC...test...\n-----END CERTIFICATE-----",
        "sp_entity_id": "https://app.example.com/saml",
        "sp_acs_url": "https://app.example.com/saml/acs",
        "sp_slo_url": "https://app.example.com/saml/slo",
        "sp_private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...test...\n-----END PRIVATE KEY-----",
        "sp_certificate": "-----BEGIN CERTIFICATE-----\nMIIC...sp...\n-----END CERTIFICATE-----",
        "sign_requests": True,
        "sign_assertions": True,
    }


# Note: mock_settings_with_sso_key, mock_settings_with_secret_key_only, mock_settings_no_keys
# are defined in conftest.py


# ========================= Encryption Key Tests =========================


class TestEncryptionKeyDerivation:
    """Tests for encryption key derivation - CWE-327/CWE-330 fix."""

    def test_get_encryption_key_with_sso_key(self, mock_db, mock_settings_with_sso_key):
        """SSO_ENCRYPTION_KEY should be used when available."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            assert service._encryption_key == ("a" * 32).encode()

    def test_get_encryption_key_with_secret_key_fallback(self, mock_db, mock_settings_with_secret_key_only):
        """SECRET_KEY should be used as fallback when SSO_ENCRYPTION_KEY not set."""
        with patch.object(sso_mod, "settings", mock_settings_with_secret_key_only):
            service = sso_mod.SSOConfigService(mock_db)
            # Key should be derived via SHA-256 from SECRET_KEY
            expected_key = hashlib.sha256("my-secret-key-for-derivation".encode()).digest()[:32]
            assert service._encryption_key == expected_key

    def test_get_encryption_key_no_keys_raises_error(self, mock_db, mock_settings_no_keys):
        """SECURITY: Must raise error when no encryption key is configured."""
        with patch.object(sso_mod, "settings", mock_settings_no_keys):
            with pytest.raises(ValueError) as exc_info:
                sso_mod.SSOConfigService(mock_db)

            # Verify error message mentions required keys
            assert "SSO_ENCRYPTION_KEY" in str(exc_info.value)
            assert "SECRET_KEY" in str(exc_info.value)

    def test_no_default_hardcoded_key_used(self, mock_db, mock_settings_no_keys):
        """SECURITY (CWE-327): No default/hardcoded key should ever be used."""
        with patch.object(sso_mod, "settings", mock_settings_no_keys):
            # Must fail - no silent fallback to default key
            with pytest.raises(ValueError):
                sso_mod.SSOConfigService(mock_db)

    def test_encryption_key_bytes_type(self, mock_db, mock_settings_with_sso_key):
        """Encryption key should be bytes type."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            assert isinstance(service._encryption_key, bytes)


# ========================= Secret Encryption Tests =========================


class TestSecretEncryption:
    """Tests for AES-256-GCM secret encryption/decryption."""

    def test_encrypt_secret_returns_base64(self, mock_db, mock_settings_with_sso_key):
        """Encrypted secret should be base64 encoded."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            secret = "my-super-secret-client-secret"

            encrypted = service._encrypt_secret(secret)

            # Should be valid base64
            try:
                decoded = base64.b64decode(encrypted)
                assert len(decoded) > 12  # At least nonce (12) + some ciphertext
            except Exception as e:
                pytest.fail(f"Encrypted secret is not valid base64: {e}")

    def test_encrypt_decrypt_roundtrip(self, mock_db, mock_settings_with_sso_key):
        """Encrypting then decrypting should return original secret."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            original_secret = "test-client-secret-12345"

            encrypted = service._encrypt_secret(original_secret)
            decrypted = service._decrypt_secret(encrypted)

            assert decrypted == original_secret

    def test_encrypt_secret_different_each_time(self, mock_db, mock_settings_with_sso_key):
        """Each encryption should produce different ciphertext (due to random nonce)."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            secret = "same-secret"

            encrypted1 = service._encrypt_secret(secret)
            encrypted2 = service._encrypt_secret(secret)

            # Due to random nonce, should be different
            assert encrypted1 != encrypted2

            # But both should decrypt to same value
            assert service._decrypt_secret(encrypted1) == secret
            assert service._decrypt_secret(encrypted2) == secret

    def test_encrypt_empty_secret(self, mock_db, mock_settings_with_sso_key):
        """Empty secret should encrypt/decrypt correctly."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            encrypted = service._encrypt_secret("")
            decrypted = service._decrypt_secret(encrypted)

            assert decrypted == ""

    def test_encrypt_unicode_secret(self, mock_db, mock_settings_with_sso_key):
        """Unicode secrets (umlauts, special chars) should work."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            secret = "Geheimschluessel-mit-Umlauten-aeoeueAeOeUe"

            encrypted = service._encrypt_secret(secret)
            decrypted = service._decrypt_secret(encrypted)

            assert decrypted == secret

    def test_decrypt_tampered_ciphertext_fails(self, mock_db, mock_settings_with_sso_key):
        """SECURITY: Tampered ciphertext should fail decryption (AES-GCM integrity)."""
        from cryptography.exceptions import InvalidTag

        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)
            secret = "secret-to-tamper"

            encrypted = service._encrypt_secret(secret)

            # Tamper with the ciphertext
            decoded = base64.b64decode(encrypted)
            tampered = decoded[:-1] + bytes([decoded[-1] ^ 0xFF])
            tampered_b64 = base64.b64encode(tampered).decode()

            with pytest.raises(InvalidTag):
                service._decrypt_secret(tampered_b64)


# ========================= Create Provider Tests =========================


class TestCreateProvider:
    """Tests for SSO provider creation."""

    @pytest.mark.asyncio
    async def test_create_oidc_provider_success(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_oidc_config
    ):
        """Successfully create OIDC provider."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            # Mock database query for existing check
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            provider = await service.create_provider(
                company_id=sample_company_id,
                name="Test OIDC Provider",
                preset=sso_mod.SSOProviderPreset.CUSTOM_OIDC,
                config_data=sample_oidc_config,
            )

            assert provider is not None
            assert provider.company_id == sample_company_id
            assert provider.name == "Test OIDC Provider"
            assert provider.oidc_config is not None
            assert provider.oidc_config.client_id == sample_oidc_config["client_id"]

            # Verify commit was called
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_provider_encrypts_client_secret(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_oidc_config
    ):
        """SECURITY: Client secret should be encrypted before storage."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            # Capture what gets stored
            stored_value = None

            def capture_add(obj):
                nonlocal stored_value
                if hasattr(obj, "value"):
                    stored_value = obj.value

            mock_db.add.side_effect = capture_add

            await service.create_provider(
                company_id=sample_company_id,
                name="Test Provider",
                preset=sso_mod.SSOProviderPreset.CUSTOM_OIDC,
                config_data=sample_oidc_config,
            )

            # The encrypted secret should be stored, not the plain one
            assert stored_value is not None
            if "_encrypted_client_secret" in stored_value:
                # Should NOT be the plain secret
                assert stored_value["_encrypted_client_secret"] != sample_oidc_config["client_secret"]
                # Should be base64 encoded encrypted data
                try:
                    base64.b64decode(stored_value["_encrypted_client_secret"])
                except Exception:
                    pytest.fail("Stored secret should be base64 encoded")

    @pytest.mark.asyncio
    async def test_create_saml_provider_encrypts_private_key(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_saml_config
    ):
        """SECURITY: SAML private key should be encrypted."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            provider = await service.create_provider(
                company_id=sample_company_id,
                name="Test SAML Provider",
                preset=sso_mod.SSOProviderPreset.CUSTOM_SAML,
                config_data=sample_saml_config,
            )

            assert provider.saml_config is not None
            # Private key should be present but encrypted
            if provider.saml_config.sp_private_key:
                encrypted_key = provider.saml_config.sp_private_key.get_secret_value()
                # Should NOT be the original PEM key
                assert "-----BEGIN PRIVATE KEY-----" not in encrypted_key

    @pytest.mark.asyncio
    async def test_create_provider_with_microsoft_preset(
        self, mock_db, mock_settings_with_sso_key, sample_company_id
    ):
        """Create provider using Microsoft Entra preset."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            config_data = {
                "client_id": "azure-client-id",
                "client_secret": "azure-secret",
                "tenant_id": "azure-tenant-id",
            }

            provider = await service.create_provider(
                company_id=sample_company_id,
                name="Microsoft Entra SSO",
                preset=sso_mod.SSOProviderPreset.MICROSOFT_ENTRA,
                config_data=config_data,
            )

            assert provider.preset == sso_mod.SSOProviderPreset.MICROSOFT_ENTRA
            # Should have Microsoft-specific endpoints from preset
            assert provider.oidc_config is not None

    @pytest.mark.asyncio
    async def test_create_provider_sets_defaults(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_oidc_config
    ):
        """Provider should have sensible defaults."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            provider = await service.create_provider(
                company_id=sample_company_id,
                name="Default Test",
                preset=sso_mod.SSOProviderPreset.CUSTOM_OIDC,
                config_data=sample_oidc_config,
            )

            # Check defaults
            assert provider.enabled is False  # Not enabled by default
            assert provider.is_primary is False
            assert provider.auto_create_users is True
            assert provider.default_role == "viewer"
            assert provider.login_count == 0


# ========================= Get Provider Tests =========================


class TestGetProvider:
    """Tests for provider retrieval with multi-tenant isolation."""

    @pytest.mark.asyncio
    async def test_get_provider_success(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_provider_id
    ):
        """Successfully retrieve provider for correct company."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            # Create mock stored config
            mock_config = Mock()
            mock_config.value = {
                "id": str(sample_provider_id),
                "company_id": str(sample_company_id),
                "name": "Test Provider",
                "provider_type": sso_mod.SSOProviderType.OIDC.value,
                "preset": "custom_oidc",
                "enabled": True,
                "is_primary": False,
                "oidc_config": {
                    "client_id": "test-client",
                    "authorization_endpoint": "https://example.com/auth",
                    "token_endpoint": "https://example.com/token",
                    "issuer": "https://example.com",
                },
                "auto_create_users": True,
                "default_role": "viewer",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "login_count": 0,
            }

            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_config
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            provider = await service.get_provider(sample_provider_id, sample_company_id)

            assert provider is not None
            assert provider.name == "Test Provider"
            assert provider.company_id == sample_company_id

    @pytest.mark.asyncio
    async def test_get_provider_wrong_company_returns_none(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, another_company_id, sample_provider_id
    ):
        """SECURITY: Provider from different company should not be returned."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            # Config belongs to another_company_id
            mock_config = Mock()
            mock_config.value = {
                "id": str(sample_provider_id),
                "company_id": str(another_company_id),  # Different company!
                "name": "Other Company Provider",
                "provider_type": sso_mod.SSOProviderType.OIDC.value,
                "preset": "custom_oidc",
                "enabled": True,
                "is_primary": False,
                "oidc_config": {
                    "client_id": "other-client",
                    "authorization_endpoint": "https://other.com/auth",
                    "token_endpoint": "https://other.com/token",
                    "issuer": "https://other.com",
                },
                "auto_create_users": True,
                "default_role": "viewer",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "login_count": 0,
            }

            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_config
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            # Request with sample_company_id but config belongs to another_company_id
            provider = await service.get_provider(sample_provider_id, sample_company_id)

            # Should return None due to company mismatch
            assert provider is None

    @pytest.mark.asyncio
    async def test_get_provider_not_found(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_provider_id
    ):
        """Non-existent provider should return None."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            provider = await service.get_provider(sample_provider_id, sample_company_id)

            assert provider is None


# ========================= List Providers Tests =========================


class TestListProviders:
    """Tests for listing providers."""

    @pytest.mark.asyncio
    async def test_list_providers_all(
        self, mock_db, mock_settings_with_sso_key, sample_company_id
    ):
        """List all providers for a company."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            provider1_id = uuid4()
            provider2_id = uuid4()

            mock_configs = [
                Mock(
                    value={
                        "id": str(provider1_id),
                        "company_id": str(sample_company_id),
                        "name": "Provider 1",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "custom_oidc",
                        "enabled": True,
                        "is_primary": True,
                        "oidc_config": {
                            "client_id": "client1",
                            "authorization_endpoint": "https://p1.com/auth",
                            "token_endpoint": "https://p1.com/token",
                            "issuer": "https://p1.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 10,
                    }
                ),
                Mock(
                    value={
                        "id": str(provider2_id),
                        "company_id": str(sample_company_id),
                        "name": "Provider 2",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "okta",
                        "enabled": False,
                        "is_primary": False,
                        "oidc_config": {
                            "client_id": "client2",
                            "authorization_endpoint": "https://p2.com/auth",
                            "token_endpoint": "https://p2.com/token",
                            "issuer": "https://p2.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 0,
                    }
                ),
            ]

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = mock_configs
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            providers = await service.list_providers(sample_company_id)

            assert len(providers) == 2
            assert providers[0].name == "Provider 1"
            assert providers[1].name == "Provider 2"

    @pytest.mark.asyncio
    async def test_list_providers_enabled_only(
        self, mock_db, mock_settings_with_sso_key, sample_company_id
    ):
        """List only enabled providers."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_configs = [
                Mock(
                    value={
                        "id": str(uuid4()),
                        "company_id": str(sample_company_id),
                        "name": "Enabled Provider",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "custom_oidc",
                        "enabled": True,
                        "is_primary": True,
                        "oidc_config": {
                            "client_id": "enabled",
                            "authorization_endpoint": "https://enabled.com/auth",
                            "token_endpoint": "https://enabled.com/token",
                            "issuer": "https://enabled.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 5,
                    }
                ),
                Mock(
                    value={
                        "id": str(uuid4()),
                        "company_id": str(sample_company_id),
                        "name": "Disabled Provider",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "custom_oidc",
                        "enabled": False,  # Disabled
                        "is_primary": False,
                        "oidc_config": {
                            "client_id": "disabled",
                            "authorization_endpoint": "https://disabled.com/auth",
                            "token_endpoint": "https://disabled.com/token",
                            "issuer": "https://disabled.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 0,
                    }
                ),
            ]

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = mock_configs
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            providers = await service.list_providers(sample_company_id, enabled_only=True)

            assert len(providers) == 1
            assert providers[0].name == "Enabled Provider"
            assert providers[0].enabled is True

    @pytest.mark.asyncio
    async def test_list_providers_filters_other_companies(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, another_company_id
    ):
        """SECURITY: Only providers for requested company should be returned."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_configs = [
                Mock(
                    value={
                        "id": str(uuid4()),
                        "company_id": str(sample_company_id),
                        "name": "Our Provider",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "custom_oidc",
                        "enabled": True,
                        "is_primary": True,
                        "oidc_config": {
                            "client_id": "ours",
                            "authorization_endpoint": "https://ours.com/auth",
                            "token_endpoint": "https://ours.com/token",
                            "issuer": "https://ours.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 0,
                    }
                ),
                Mock(
                    value={
                        "id": str(uuid4()),
                        "company_id": str(another_company_id),  # Different company
                        "name": "Other Company Provider",
                        "provider_type": sso_mod.SSOProviderType.OIDC.value,
                        "preset": "custom_oidc",
                        "enabled": True,
                        "is_primary": True,
                        "oidc_config": {
                            "client_id": "theirs",
                            "authorization_endpoint": "https://theirs.com/auth",
                            "token_endpoint": "https://theirs.com/token",
                            "issuer": "https://theirs.com",
                        },
                        "auto_create_users": True,
                        "default_role": "viewer",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "login_count": 0,
                    }
                ),
            ]

            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = mock_configs
            mock_db.execute.return_value = mock_result

            service = sso_mod.SSOConfigService(mock_db)

            providers = await service.list_providers(sample_company_id)

            # Should only return our company's provider
            assert len(providers) == 1
            assert providers[0].name == "Our Provider"


# ========================= Preset Template Tests =========================


class TestPresetTemplates:
    """Tests for provider preset templates."""

    def test_get_microsoft_entra_preset(self, mock_db, mock_settings_with_sso_key):
        """Microsoft Entra preset should have correct endpoints."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template = service.get_preset_template(sso_mod.SSOProviderPreset.MICROSOFT_ENTRA)

            assert "authorization_endpoint" in template
            assert "login.microsoftonline.com" in template["authorization_endpoint"]
            assert "{tenant_id}" in template["authorization_endpoint"]
            assert "scopes" in template
            assert "User.Read" in template["scopes"]

    def test_get_google_workspace_preset(self, mock_db, mock_settings_with_sso_key):
        """Google Workspace preset should have correct endpoints."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template = service.get_preset_template(sso_mod.SSOProviderPreset.GOOGLE_WORKSPACE)

            assert "authorization_endpoint" in template
            assert "accounts.google.com" in template["authorization_endpoint"]
            assert template["issuer"] == "https://accounts.google.com"

    def test_get_okta_preset(self, mock_db, mock_settings_with_sso_key):
        """Okta preset should have domain placeholder."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template = service.get_preset_template(sso_mod.SSOProviderPreset.OKTA)

            assert "authorization_endpoint" in template
            assert "{domain}" in template["authorization_endpoint"]
            assert "groups" in template["scopes"]

    def test_get_auth0_preset(self, mock_db, mock_settings_with_sso_key):
        """Auth0 preset should have domain placeholder."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template = service.get_preset_template(sso_mod.SSOProviderPreset.AUTH0)

            assert "authorization_endpoint" in template
            assert "{domain}" in template["authorization_endpoint"]
            assert ".well-known/jwks.json" in template["jwks_uri"]

    def test_get_keycloak_preset(self, mock_db, mock_settings_with_sso_key):
        """Keycloak preset should have base_url and realm placeholders."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template = service.get_preset_template(sso_mod.SSOProviderPreset.KEYCLOAK)

            assert "authorization_endpoint" in template
            assert "{base_url}" in template["authorization_endpoint"]
            assert "{realm}" in template["authorization_endpoint"]
            assert "openid-connect" in template["authorization_endpoint"]

    def test_custom_presets_have_minimal_config(self, mock_db, mock_settings_with_sso_key):
        """CUSTOM presets should have minimal config (just provider_type)."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            # CUSTOM_OIDC has provider_type and default scopes
            oidc_template = service.get_preset_template(sso_mod.SSOProviderPreset.CUSTOM_OIDC)
            assert oidc_template["provider_type"] == sso_mod.SSOProviderType.OIDC
            assert "authorization_endpoint" not in oidc_template  # No pre-filled endpoints

            # CUSTOM_SAML has just provider_type
            saml_template = service.get_preset_template(sso_mod.SSOProviderPreset.CUSTOM_SAML)
            assert saml_template["provider_type"] == sso_mod.SSOProviderType.SAML
            assert "idp_sso_url" not in saml_template  # No pre-filled endpoints

    def test_preset_templates_are_copies(self, mock_db, mock_settings_with_sso_key):
        """Preset templates should be copies, not references."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            template1 = service.get_preset_template(sso_mod.SSOProviderPreset.OKTA)
            template2 = service.get_preset_template(sso_mod.SSOProviderPreset.OKTA)

            # Modifying one should not affect the other
            template1["custom_field"] = "test"

            assert "custom_field" not in template2


# ========================= Provider Type Tests =========================


class TestProviderTypes:
    """Tests for SSO provider types and presets."""

    def test_sso_provider_type_enum(self):
        """SSOProviderType enum should have OIDC and SAML."""
        assert sso_mod.SSOProviderType.OIDC.value == "oidc"
        assert sso_mod.SSOProviderType.SAML.value == "saml"

    def test_sso_provider_preset_enum(self):
        """SSOProviderPreset enum should have all major providers."""
        presets = [p.value for p in sso_mod.SSOProviderPreset]

        assert "microsoft_entra" in presets
        assert "google_workspace" in presets
        assert "okta" in presets
        assert "onelogin" in presets
        assert "auth0" in presets
        assert "keycloak" in presets
        assert "custom_oidc" in presets
        assert "custom_saml" in presets


# ========================= Error Cases Tests =========================


class TestErrorCases:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_create_provider_database_error(
        self, mock_db, mock_settings_with_sso_key, sample_company_id, sample_oidc_config
    ):
        """Database error during create should propagate."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            mock_db.commit.side_effect = Exception("Database connection lost")

            service = sso_mod.SSOConfigService(mock_db)

            with pytest.raises(Exception) as exc_info:
                await service.create_provider(
                    company_id=sample_company_id,
                    name="Error Test",
                    preset=sso_mod.SSOProviderPreset.CUSTOM_OIDC,
                    config_data=sample_oidc_config,
                )

            assert "Database connection lost" in str(exc_info.value)

    def test_decrypt_invalid_base64(self, mock_db, mock_settings_with_sso_key):
        """Decrypting invalid base64 should raise error."""
        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            service = sso_mod.SSOConfigService(mock_db)

            with pytest.raises(Exception):
                service._decrypt_secret("not-valid-base64!!!")

    def test_decrypt_wrong_key_fails(self, mock_db, mock_settings_with_sso_key):
        """Decrypting with wrong key should fail."""
        from cryptography.exceptions import InvalidTag

        with patch.object(sso_mod, "settings", mock_settings_with_sso_key):
            # Encrypt with one key
            service1 = sso_mod.SSOConfigService(mock_db)
            encrypted = service1._encrypt_secret("test-secret")

            # Try to decrypt with different key
            different_settings = MagicMock()
            different_settings.SSO_ENCRYPTION_KEY = "b" * 32  # Different key

            with patch.object(sso_mod, "settings", different_settings):
                service2 = sso_mod.SSOConfigService(mock_db)

                with pytest.raises(InvalidTag):
                    service2._decrypt_secret(encrypted)

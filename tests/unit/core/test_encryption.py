"""
Unit tests for Encryption Service.

Tests:
- AES-256-GCM Verschlüsselung/Entschlüsselung
- TOTP Secret Verschlüsselung mit User-ID als AAD
- Key-Generierung und -Validierung
- Fehlerbehandlung
- Key-Rotation

Arbeitspaket 5: TOTP-Verschlüsselung
"""

import pytest
import base64
import secrets
from unittest.mock import patch, MagicMock

from app.core.encryption import (
    encrypt_data,
    decrypt_data,
    encrypt_totp_secret,
    decrypt_totp_secret,
    generate_encryption_key,
    is_encrypted,
    rotate_encryption_key,
    set_test_key,
    clear_key_cache,
    _derive_key_from_secret,
    EncryptionError,
    KeyNotConfiguredError,
    DecryptionError,
    AES_KEY_SIZE,
    NONCE_SIZE,
    TAG_SIZE,
    KDF_ITERATIONS,
    KDF_SALT,
)


@pytest.fixture(autouse=True)
def setup_test_key():
    """Setup and teardown test encryption key."""
    # Generiere Test-Key
    test_key = secrets.token_bytes(AES_KEY_SIZE)
    set_test_key(test_key)
    yield
    # Cleanup
    set_test_key(None)
    clear_key_cache()


class TestKeyGeneration:
    """Tests für Key-Generierung."""

    def test_generate_encryption_key_returns_base64(self):
        """Key-Generierung gibt Base64-String zurück."""
        key = generate_encryption_key()

        assert isinstance(key, str)
        # Sollte Base64-decodierbar sein
        decoded = base64.b64decode(key)
        assert len(decoded) == AES_KEY_SIZE

    def test_generate_encryption_key_unique(self):
        """Jeder generierte Key ist einzigartig."""
        keys = [generate_encryption_key() for _ in range(10)]

        assert len(set(keys)) == 10


class TestEncryptDecrypt:
    """Tests für Encrypt/Decrypt-Funktionen."""

    def test_encrypt_decrypt_roundtrip(self):
        """Verschlüsseln und Entschlüsseln gibt Original zurück."""
        plaintext = "Geheimer TOTP-Secret: JBSWY3DPEHPK3PXP"

        encrypted = encrypt_data(plaintext)
        decrypted = decrypt_data(encrypted)

        assert decrypted == plaintext

    def test_encrypt_returns_base64(self):
        """Verschlüsselung gibt Base64-String zurück."""
        plaintext = "Test-Daten"

        encrypted = encrypt_data(plaintext)

        assert isinstance(encrypted, str)
        # Sollte Base64-decodierbar sein
        decoded = base64.b64decode(encrypted)
        # Mindestens Nonce + Tag
        assert len(decoded) >= NONCE_SIZE + TAG_SIZE

    def test_encrypt_different_nonces(self):
        """Jede Verschlüsselung verwendet andere Nonce."""
        plaintext = "Same plaintext"

        encrypted1 = encrypt_data(plaintext)
        encrypted2 = encrypt_data(plaintext)

        # Ciphertext sollte unterschiedlich sein (wegen Nonce)
        assert encrypted1 != encrypted2

    def test_decrypt_with_wrong_ciphertext_fails(self):
        """Entschlüsselung mit falschen Daten schlägt fehl."""
        # Generiere valide verschlüsselte Daten
        encrypted = encrypt_data("Original")

        # Manipuliere Ciphertext
        decoded = bytearray(base64.b64decode(encrypted))
        decoded[-1] ^= 0xFF  # Flip last byte
        tampered = base64.b64encode(bytes(decoded)).decode('utf-8')

        with pytest.raises(DecryptionError):
            decrypt_data(tampered)

    def test_decrypt_too_short_data_fails(self):
        """Zu kurze Daten führen zu DecryptionError."""
        short_data = base64.b64encode(b"short").decode('utf-8')

        with pytest.raises(DecryptionError) as exc_info:
            decrypt_data(short_data)

        assert "too short" in str(exc_info.value).lower()

    def test_encrypt_empty_string(self):
        """Leerer String kann verschlüsselt werden."""
        encrypted = encrypt_data("")
        decrypted = decrypt_data(encrypted)

        assert decrypted == ""

    def test_encrypt_unicode(self):
        """Unicode-Zeichen werden korrekt behandelt."""
        plaintext = "Geheim: äöü ß 中文 🔐"

        encrypted = encrypt_data(plaintext)
        decrypted = decrypt_data(encrypted)

        assert decrypted == plaintext

    def test_encrypt_long_data(self):
        """Lange Daten können verschlüsselt werden."""
        plaintext = "A" * 10000

        encrypted = encrypt_data(plaintext)
        decrypted = decrypt_data(encrypted)

        assert decrypted == plaintext


class TestAssociatedData:
    """Tests für Associated Authenticated Data (AAD)."""

    def test_encrypt_with_aad(self):
        """Verschlüsselung mit AAD funktioniert."""
        plaintext = "Secret"
        aad = "user:12345"

        encrypted = encrypt_data(plaintext, associated_data=aad)
        decrypted = decrypt_data(encrypted, associated_data=aad)

        assert decrypted == plaintext

    def test_decrypt_wrong_aad_fails(self):
        """Entschlüsselung mit falscher AAD schlägt fehl."""
        plaintext = "Secret"
        correct_aad = "user:12345"
        wrong_aad = "user:99999"

        encrypted = encrypt_data(plaintext, associated_data=correct_aad)

        with pytest.raises(DecryptionError):
            decrypt_data(encrypted, associated_data=wrong_aad)

    def test_decrypt_missing_aad_fails(self):
        """Entschlüsselung ohne AAD schlägt fehl wenn AAD erwartet."""
        plaintext = "Secret"
        aad = "user:12345"

        encrypted = encrypt_data(plaintext, associated_data=aad)

        with pytest.raises(DecryptionError):
            decrypt_data(encrypted)  # Keine AAD

    def test_decrypt_unexpected_aad_fails(self):
        """Entschlüsselung mit unerwarteter AAD schlägt fehl."""
        plaintext = "Secret"

        encrypted = encrypt_data(plaintext)  # Keine AAD

        with pytest.raises(DecryptionError):
            decrypt_data(encrypted, associated_data="unexpected")


class TestTOTPSecretEncryption:
    """Tests für TOTP-spezifische Verschlüsselung."""

    def test_encrypt_totp_secret_roundtrip(self):
        """TOTP Secret Verschlüsselung Roundtrip."""
        secret = "JBSWY3DPEHPK3PXP"
        user_id = "550e8400-e29b-41d4-a716-446655440000"

        encrypted = encrypt_totp_secret(secret, user_id)
        decrypted = decrypt_totp_secret(encrypted, user_id)

        assert decrypted == secret

    def test_totp_secret_different_user_fails(self):
        """TOTP Secret kann nicht mit anderer User-ID entschlüsselt werden."""
        secret = "JBSWY3DPEHPK3PXP"
        user_id_1 = "550e8400-e29b-41d4-a716-446655440001"
        user_id_2 = "550e8400-e29b-41d4-a716-446655440002"

        encrypted = encrypt_totp_secret(secret, user_id_1)

        with pytest.raises(DecryptionError):
            decrypt_totp_secret(encrypted, user_id_2)

    def test_totp_aad_format(self):
        """AAD verwendet korrektes Format."""
        secret = "JBSWY3DPEHPK3PXP"
        user_id = "test-user"

        # Verschlüssele direkt mit AAD
        encrypted_direct = encrypt_data(secret, associated_data=f"totp:{user_id}")

        # Sollte mit decrypt_totp_secret entschlüsselbar sein
        decrypted = decrypt_totp_secret(encrypted_direct, user_id)
        assert decrypted == secret


class TestIsEncrypted:
    """Tests für is_encrypted Heuristik."""

    def test_is_encrypted_true_for_encrypted_data(self):
        """Erkennt verschlüsselte Daten."""
        encrypted = encrypt_data("test")

        assert is_encrypted(encrypted) is True

    def test_is_encrypted_false_for_plain_text(self):
        """Erkennt Klartext als nicht verschlüsselt."""
        plaintext = "JBSWY3DPEHPK3PXP"

        assert is_encrypted(plaintext) is False

    def test_is_encrypted_false_for_short_base64(self):
        """Kurze Base64-Daten sind nicht verschlüsselt."""
        short_b64 = base64.b64encode(b"short").decode('utf-8')

        assert is_encrypted(short_b64) is False

    def test_is_encrypted_false_for_invalid_base64(self):
        """Ungültiges Base64 ist nicht verschlüsselt."""
        invalid = "not-valid-base64!!!"

        assert is_encrypted(invalid) is False


class TestKeyRotation:
    """Tests für Key-Rotation."""

    def test_rotate_encryption_key(self):
        """Key-Rotation funktioniert korrekt."""
        # Setup Keys
        old_key = secrets.token_bytes(AES_KEY_SIZE)
        new_key = secrets.token_bytes(AES_KEY_SIZE)

        # Verschlüssele mit altem Key
        set_test_key(old_key)
        plaintext = "Secret Data"
        encrypted_old = encrypt_data(plaintext)

        # Rotiere
        encrypted_new = rotate_encryption_key(
            old_key=old_key,
            new_key=new_key,
            ciphertext=encrypted_old
        )

        # Entschlüssele mit neuem Key
        set_test_key(new_key)
        decrypted = decrypt_data(encrypted_new)

        assert decrypted == plaintext

    def test_rotate_encryption_key_with_aad(self):
        """Key-Rotation mit AAD."""
        old_key = secrets.token_bytes(AES_KEY_SIZE)
        new_key = secrets.token_bytes(AES_KEY_SIZE)
        aad = "user:12345"

        # Verschlüssele mit altem Key
        set_test_key(old_key)
        plaintext = "Secret Data"
        encrypted_old = encrypt_data(plaintext, associated_data=aad)

        # Rotiere
        encrypted_new = rotate_encryption_key(
            old_key=old_key,
            new_key=new_key,
            ciphertext=encrypted_old,
            associated_data=aad
        )

        # Entschlüssele mit neuem Key
        set_test_key(new_key)
        decrypted = decrypt_data(encrypted_new, associated_data=aad)

        assert decrypted == plaintext


class TestKeyNotConfigured:
    """Tests für fehlende Key-Konfiguration."""

    def test_encrypt_without_key_fails(self):
        """Verschlüsselung ohne Key schlägt fehl."""
        clear_key_cache()
        set_test_key(None)

        # Mock settings to return no keys
        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            mock_settings.SECRET_KEY = None

            with pytest.raises(KeyNotConfiguredError):
                encrypt_data("test")

    def test_decrypt_without_key_fails(self):
        """Entschlüsselung ohne Key schlägt fehl."""
        clear_key_cache()
        set_test_key(None)

        # Mock settings to return no keys
        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            mock_settings.SECRET_KEY = None

            with pytest.raises(KeyNotConfiguredError):
                decrypt_data("some-encrypted-data")


class TestKeyDerivation:
    """Tests für Key-Ableitung aus SECRET_KEY."""

    def test_key_derived_from_secret_key(self):
        """Key wird aus SECRET_KEY abgeleitet wenn ENCRYPTION_KEY fehlt."""
        clear_key_cache()
        set_test_key(None)

        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            mock_settings.SECRET_KEY = "test-secret-key-for-derivation"

            # Sollte funktionieren mit abgeleitetem Key
            plaintext = "test"
            encrypted = encrypt_data(plaintext)
            decrypted = decrypt_data(encrypted)

            assert decrypted == plaintext


class TestEdgeCases:
    """Tests für Randfälle."""

    def test_encrypt_special_characters(self):
        """Spezialzeichen werden korrekt behandelt."""
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

        encrypted = encrypt_data(special_chars)
        decrypted = decrypt_data(encrypted)

        assert decrypted == special_chars

    def test_encrypt_newlines(self):
        """Zeilenumbrüche werden korrekt behandelt."""
        with_newlines = "Line 1\nLine 2\r\nLine 3"

        encrypted = encrypt_data(with_newlines)
        decrypted = decrypt_data(encrypted)

        assert decrypted == with_newlines

    def test_encrypt_binary_like_string(self):
        """Binär-ähnliche Strings werden korrekt behandelt."""
        binary_like = "\x00\x01\x02\x03"

        encrypted = encrypt_data(binary_like)
        decrypted = decrypt_data(encrypted)

        assert decrypted == binary_like


class TestPBKDF2KeyDerivation:
    """
    Tests für PBKDF2-basierte Key-Derivation.

    Stellt sicher, dass die Key-Derivation:
    - Deterministisch ist (gleicher Input = gleicher Output)
    - NIST-konforme Parameter verwendet
    - Sicher gegen Rainbow-Table-Angriffe ist
    """

    def test_derive_key_returns_correct_length(self):
        """Abgeleiteter Key hat korrekte Länge (32 Bytes für AES-256)."""
        key = _derive_key_from_secret("test-secret")

        assert len(key) == AES_KEY_SIZE
        assert len(key) == 32  # 256 bits

    def test_derive_key_is_deterministic(self):
        """Gleicher Input ergibt immer gleichen Key."""
        secret = "my-secret-key-for-testing"

        key1 = _derive_key_from_secret(secret)
        key2 = _derive_key_from_secret(secret)

        assert key1 == key2

    def test_derive_key_different_inputs_different_outputs(self):
        """Unterschiedliche Inputs ergeben unterschiedliche Keys."""
        key1 = _derive_key_from_secret("secret-1")
        key2 = _derive_key_from_secret("secret-2")

        assert key1 != key2

    def test_derive_key_case_sensitive(self):
        """Key-Derivation ist case-sensitive."""
        key_lower = _derive_key_from_secret("secret")
        key_upper = _derive_key_from_secret("SECRET")

        assert key_lower != key_upper

    def test_kdf_iterations_nist_compliant(self):
        """KDF verwendet mindestens 10.000 Iterationen (NIST Empfehlung)."""
        # NIST SP 800-132 empfiehlt mindestens 10.000 Iterationen
        assert KDF_ITERATIONS >= 10000
        # Wir verwenden 100.000 für zusätzliche Sicherheit
        assert KDF_ITERATIONS == 100000

    def test_kdf_salt_is_set(self):
        """KDF verwendet einen Salt."""
        assert KDF_SALT is not None
        assert len(KDF_SALT) > 0

    def test_derive_key_returns_bytes(self):
        """Abgeleiteter Key ist vom Typ bytes."""
        key = _derive_key_from_secret("test")

        assert isinstance(key, bytes)

    def test_derive_key_handles_unicode(self):
        """Key-Derivation funktioniert mit Unicode."""
        key = _derive_key_from_secret("geheim-äöü-中文")

        assert len(key) == AES_KEY_SIZE

    def test_derive_key_handles_empty_string(self):
        """Key-Derivation funktioniert mit leerem String."""
        # Leerer String ist gültig (auch wenn nicht empfohlen)
        key = _derive_key_from_secret("")

        assert len(key) == AES_KEY_SIZE

    def test_derive_key_handles_long_secret(self):
        """Key-Derivation funktioniert mit langem Secret."""
        long_secret = "A" * 10000
        key = _derive_key_from_secret(long_secret)

        assert len(key) == AES_KEY_SIZE

    def test_encryption_with_derived_key_works(self):
        """Verschlüsselung mit abgeleitetem Key funktioniert Ende-zu-Ende."""
        clear_key_cache()
        set_test_key(None)

        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            # Simuliere SecretStr
            mock_secret = MagicMock()
            mock_secret.get_secret_value.return_value = "test-secret-key"
            mock_settings.SECRET_KEY = mock_secret

            plaintext = "Geheime Daten für Test"
            encrypted = encrypt_data(plaintext)
            decrypted = decrypt_data(encrypted)

            assert decrypted == plaintext

    def test_derived_key_changes_with_different_secret(self):
        """Unterschiedliche SECRET_KEYs ergeben unterschiedliche Verschlüsselungen."""
        clear_key_cache()
        set_test_key(None)

        plaintext = "Test Data"

        # Verschlüssele mit erstem Secret
        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            mock_secret1 = MagicMock()
            mock_secret1.get_secret_value.return_value = "secret-key-1"
            mock_settings.SECRET_KEY = mock_secret1

            encrypted1 = encrypt_data(plaintext)

        clear_key_cache()

        # Verschlüssele mit zweitem Secret
        with patch('app.core.encryption.settings') as mock_settings:
            mock_settings.ENCRYPTION_KEY = None
            mock_secret2 = MagicMock()
            mock_secret2.get_secret_value.return_value = "secret-key-2"
            mock_settings.SECRET_KEY = mock_secret2

            encrypted2 = encrypt_data(plaintext)

        # Ciphertexts sollten unterschiedlich sein
        # (wegen unterschiedlicher Keys + unterschiedlicher Nonces)
        assert encrypted1 != encrypted2

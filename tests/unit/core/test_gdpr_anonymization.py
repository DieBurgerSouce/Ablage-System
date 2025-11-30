"""Unit tests für GDPR Anonymisierung und Pseudonymisierung.

Testet SHA-256 basierte Anonymisierung für:
- Sozialversicherungsnummer
- Steuer-ID
- IBAN
- E-Mail
- Telefonnummer
- Namen
- IP-Adressen
"""

import pytest

from app.core.gdpr import GDPRComplianceManager


class TestAnonymizationPlaceholders:
    """Tests für Anonymisierung mit Platzhaltern."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_anonymize_ssn(self, gdpr_manager):
        """Sozialversicherungsnummer sollte anonymisiert werden."""
        text = "SSN: 12 345678 A 123"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=False)

        assert "12 345678 A 123" not in result
        assert "[SSN_ANONYMIZED]" in result

    def test_anonymize_tax_id(self, gdpr_manager):
        """Steuer-ID sollte anonymisiert werden."""
        text = "Steuer-ID: 12345678901"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=False)

        assert "12345678901" not in result
        assert "[TAX_ID_ANONYMIZED]" in result

    def test_anonymize_iban(self, gdpr_manager):
        """IBAN sollte anonymisiert werden."""
        text = "IBAN: DE89370400440532013000"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=False)

        assert "DE89370400440532013000" not in result
        assert "DE********************" in result

    def test_anonymize_email(self, gdpr_manager):
        """E-Mail sollte anonymisiert werden."""
        text = "Kontakt: test.user@example.com"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=False)

        assert "test.user@example.com" not in result
        assert "[EMAIL_ANONYMIZED]" in result

    def test_anonymize_phone(self, gdpr_manager):
        """Telefonnummer sollte anonymisiert werden."""
        text = "Tel: +49 1234 567890"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=False)

        assert "+49 1234 567890" not in result
        assert "[PHONE_ANONYMIZED]" in result


class TestPseudonymizationSHA256:
    """Tests für SHA-256 basierte Pseudonymisierung."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_pseudonymize_ssn(self, gdpr_manager):
        """SSN sollte mit SHA-256 Hash pseudonymisiert werden."""
        text = "SSN: 12 345678 A 123"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=True)

        assert "12 345678 A 123" not in result
        assert "[SSN:" in result
        # Hash sollte 16 Zeichen haben
        assert len(result.split("[SSN:")[1].split("]")[0]) == 16

    def test_pseudonymize_consistency(self, gdpr_manager):
        """Gleiche PII sollte gleichen Hash produzieren."""
        text1 = "E-Mail: test@example.com"
        text2 = "Kontakt: test@example.com"

        result1 = gdpr_manager.anonymize_text(text1, use_pseudonymization=True)
        result2 = gdpr_manager.anonymize_text(text2, use_pseudonymization=True)

        # Extrahiere Hash aus beiden
        hash1 = result1.split("[EMAIL:")[1].split("@")[0]
        hash2 = result2.split("[EMAIL:")[1].split("@")[0]

        assert hash1 == hash2  # Gleiche E-Mail = gleicher Hash

    def test_pseudonymize_email_keeps_domain(self, gdpr_manager):
        """Bei E-Mail Pseudonymisierung sollte Domain sichtbar bleiben."""
        text = "Kontakt: test@example.com"
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=True)

        assert "example.com" in result
        assert "test" not in result

    def test_pseudonymize_names(self, gdpr_manager):
        """Namen sollten pseudonymisiert werden."""
        text = "Herr Max Mustermann hat bestellt."
        result = gdpr_manager.anonymize_text(text, use_pseudonymization=True)

        assert "Max Mustermann" not in result
        assert "Herr [NAME:" in result


class TestIPAnonymization:
    """Tests für IP-Adressen Anonymisierung."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_anonymize_ipv4(self, gdpr_manager):
        """IPv4 letztes Oktett sollte auf 0 gesetzt werden."""
        ip = "192.168.1.100"
        result = gdpr_manager.anonymize_ip_address(ip)

        assert result == "192.168.1.0"

    def test_anonymize_ipv6(self, gdpr_manager):
        """IPv6 letzte Gruppen sollten anonymisiert werden."""
        ip = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        result = gdpr_manager.anonymize_ip_address(ip)

        assert result.startswith("2001:0db8:85a3:")
        assert result.count(":0") >= 5

    def test_anonymize_empty_ip(self, gdpr_manager):
        """Leere IP sollte [NO_IP] zurückgeben."""
        result = gdpr_manager.anonymize_ip_address("")
        assert result == "[NO_IP]"

        result = gdpr_manager.anonymize_ip_address(None)
        assert result == "[NO_IP]"


class TestPseudonymizeIdentifier:
    """Tests für Identifier Pseudonymisierung."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_pseudonymize_identifier_without_salt(self, gdpr_manager):
        """Identifier sollte konsistent gehasht werden."""
        identifier = "user@example.com"

        hash1 = gdpr_manager.pseudonymize_identifier(identifier)
        hash2 = gdpr_manager.pseudonymize_identifier(identifier)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 = 64 hex Zeichen

    def test_pseudonymize_identifier_with_salt(self, gdpr_manager):
        """Salt sollte unterschiedlichen Hash produzieren."""
        identifier = "user@example.com"

        hash_without_salt = gdpr_manager.pseudonymize_identifier(identifier)
        hash_with_salt = gdpr_manager.pseudonymize_identifier(identifier, salt="secret")

        assert hash_without_salt != hash_with_salt

    def test_pseudonymize_identifier_different_identifiers(self, gdpr_manager):
        """Verschiedene Identifier sollten verschiedene Hashes produzieren."""
        hash1 = gdpr_manager.pseudonymize_identifier("user1@example.com")
        hash2 = gdpr_manager.pseudonymize_identifier("user2@example.com")

        assert hash1 != hash2


class TestHashForAudit:
    """Tests für Audit-Logging Hash."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_hash_for_audit_consistent(self, gdpr_manager):
        """Audit-Hash sollte konsistent sein."""
        data = "some sensitive data"

        hash1 = gdpr_manager.hash_for_audit(data)
        hash2 = gdpr_manager.hash_for_audit(data)

        assert hash1 == hash2

    def test_hash_for_audit_length(self, gdpr_manager):
        """Audit-Hash sollte 32 Zeichen haben."""
        hash_result = gdpr_manager.hash_for_audit("test data")

        assert len(hash_result) == 32

    def test_hash_for_audit_different_data(self, gdpr_manager):
        """Verschiedene Daten sollten verschiedene Hashes produzieren."""
        hash1 = gdpr_manager.hash_for_audit("data1")
        hash2 = gdpr_manager.hash_for_audit("data2")

        assert hash1 != hash2


class TestSensitiveDataDetection:
    """Tests für Erkennung sensibler Daten."""

    @pytest.fixture
    def gdpr_manager(self):
        """Erstelle GDPR Manager Instanz."""
        return GDPRComplianceManager()

    def test_detect_email(self, gdpr_manager):
        """E-Mail sollte erkannt werden."""
        text = "Kontakt unter test@example.com"
        result = gdpr_manager.check_sensitive_data(text)

        assert result["has_sensitive_data"] is True
        assert "email" in result["data_types"]

    def test_detect_iban(self, gdpr_manager):
        """IBAN sollte erkannt werden."""
        text = "IBAN: DE89370400440532013000"
        result = gdpr_manager.check_sensitive_data(text)

        assert result["has_sensitive_data"] is True
        assert "iban" in result["data_types"]

    def test_detect_phone(self, gdpr_manager):
        """Telefonnummer sollte erkannt werden."""
        text = "Telefon: +49 123 4567890"
        result = gdpr_manager.check_sensitive_data(text)

        assert result["has_sensitive_data"] is True
        assert "phone" in result["data_types"]

    def test_no_sensitive_data(self, gdpr_manager):
        """Normaler Text ohne PII sollte keine Treffer haben."""
        text = "Dies ist ein normaler Text ohne persönliche Daten."
        result = gdpr_manager.check_sensitive_data(text)

        assert result["has_sensitive_data"] is False
        assert len(result["data_types"]) == 0

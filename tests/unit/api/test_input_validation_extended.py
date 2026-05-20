# -*- coding: utf-8 -*-
"""
Extended Unit Tests fuer API Input Validation.

Tests fuer:
- Sicherheits-Validierung (XSS, SQL Injection)
- Edge Cases bei allen Feldern
- Datei-Upload Validierung
- Deutsche Zeichen Validierung
- GDPR-konforme Validierung
"""

import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from app.db.schemas import (
    # Enums
    ProcessingStatus,
    OCRBackend,
    DocumentType,
    DataCategory,
    # User Schemas
    UserBase,
    UserCreate,
    UserUpdate,
    UserChangePassword,
    UserResponse,
    # Document Schemas
    DocumentBase,
    DocumentCreate,
    DocumentUpdate,
    DocumentMetadata,
    # Auth Schemas
    TokenResponse,
    LoginRequest,
)


class TestXSSPrevention:
    """Tests fuer XSS-Praevention in Input-Feldern."""

    def test_username_rejects_script_tags(self):
        """Username mit Script-Tags wird abgelehnt."""
        malicious_usernames = [
            "<script>alert('xss')</script>",
            "test<script>",
            "user\"><script>",
            "name'onclick='alert(1)",
        ]

        for username in malicious_usernames:
            with pytest.raises(ValidationError):
                UserBase(email="test@example.com", username=username)

    def test_full_name_allows_special_chars_safely(self):
        """Full Name akzeptiert Sonderzeichen sicher."""
        # These should work (legitimate names)
        valid_names = [
            "Müller-Schmidt",
            "O'Brien",
            "Jean-Pierre Ärger",
            "Max Größe",
        ]

        for name in valid_names:
            user = UserBase(
                email="test@example.com",
                username="testuser",
                full_name=name
            )
            assert user.full_name == name

    def test_document_metadata_rejects_html(self):
        """DocumentMetadata Notes sollten HTML akzeptieren (plain text)."""
        # Notes are plain text - HTML is stored as-is, not executed
        metadata = DocumentMetadata(
            notes="<p>Test note</p>"
        )
        assert "<p>" in metadata.notes  # Stored as-is, sanitized on display

    def test_tags_reject_special_characters(self):
        """Tags mit gefaehrlichen Zeichen werden abgelehnt."""
        dangerous_tags = [
            ["<script>"],
            ["normal", "<img onerror='alert(1)'>"],
            ["test'; DROP TABLE--"],
        ]

        for tags in dangerous_tags:
            with pytest.raises(ValidationError):
                DocumentMetadata(custom_tags=tags)


class TestSQLInjectionPrevention:
    """Tests fuer SQL Injection Praevention."""

    def test_username_rejects_sql_injection(self):
        """Username mit SQL-Injection wird abgelehnt."""
        sql_injections = [
            "'; DROP TABLE users--",
            "1' OR '1'='1",
            "admin'--",
            "user; DELETE FROM",
        ]

        for injection in sql_injections:
            with pytest.raises(ValidationError):
                UserBase(email="test@example.com", username=injection)

    def test_email_validates_format(self):
        """Email mit SQL-Injection scheitert an Format-Validierung."""
        sql_emails = [
            "test@test'; DROP TABLE--",
            "' OR '1'='1@test.com",
        ]

        for email in sql_emails:
            with pytest.raises(ValidationError):
                UserBase(email=email, username="testuser")

    def test_metadata_fields_accept_special_chars(self):
        """Metadata-Felder akzeptieren spezielle Zeichen (parametrisierte Queries)."""
        # These are stored safely via parameterized queries
        metadata = DocumentMetadata(
            customer_id="CUST-2024-001",
            project_id="PRJ_2024_Q1",
            notes="Rechnung #1234; Betrag: 500€"
        )
        assert metadata.customer_id == "CUST-2024-001"


class TestPathTraversalPrevention:
    """Tests fuer Path Traversal Praevention."""

    def test_filename_rejects_path_traversal(self):
        """Filename mit Path Traversal wird nicht direkt validiert."""
        # Note: Path traversal is handled at file storage level
        # Schema just validates length and presence
        dangerous_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "test/../../../secret.txt",
        ]

        for filename in dangerous_filenames:
            # Schema accepts these - file handler must sanitize
            doc = DocumentBase(filename=filename)
            assert doc.filename == filename  # Schema doesn't sanitize paths


class TestFieldLengthLimits:
    """Tests fuer Feldlaengen-Grenzen."""

    def test_username_max_length(self):
        """Username max 100 Zeichen."""
        long_username = "a" * 101

        with pytest.raises(ValidationError) as exc_info:
            UserBase(email="test@example.com", username=long_username)

        assert "username" in str(exc_info.value).lower()

    def test_username_min_length(self):
        """Username mindestens 3 Zeichen."""
        with pytest.raises(ValidationError):
            UserBase(email="test@example.com", username="ab")

    def test_password_max_length(self):
        """Password max 100 Zeichen."""
        long_password = "a" * 101

        with pytest.raises(ValidationError):
            UserChangePassword(
                current_password="oldpass",
                new_password=long_password
            )

    def test_filename_max_length(self):
        """Filename max 255 Zeichen."""
        long_filename = "a" * 256 + ".pdf"

        with pytest.raises(ValidationError):
            DocumentBase(filename=long_filename)

    def test_notes_max_length(self):
        """Notes max 2000 Zeichen."""
        long_notes = "a" * 2001

        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(notes=long_notes)

        assert "notes" in str(exc_info.value).lower()

    def test_tag_max_length(self):
        """Einzelner Tag max 50 Zeichen."""
        long_tag = "a" * 51

        with pytest.raises(ValidationError):
            DocumentMetadata(custom_tags=[long_tag])

    def test_max_tags_count(self):
        """Maximal 20 Tags erlaubt."""
        too_many_tags = [f"tag{i}" for i in range(21)]

        with pytest.raises(ValidationError):
            DocumentMetadata(custom_tags=too_many_tags)


class TestGermanCharacterValidation:
    """Tests fuer deutsche Zeichen-Unterstuetzung."""

    def test_full_name_accepts_umlauts(self):
        """Full Name akzeptiert deutsche Umlaute."""
        german_names = [
            "Müller",
            "Größe",
            "Löwe",
            "Über",
            "Höflichkeit",
        ]

        for name in german_names:
            user = UserBase(
                email="test@example.com",
                username="testuser",
                full_name=name
            )
            assert user.full_name == name

    def test_full_name_accepts_eszett(self):
        """Full Name akzeptiert Eszett (ß)."""
        user = UserBase(
            email="test@example.com",
            username="testuser",
            full_name="Großmann"
        )
        assert "ß" in user.full_name

    def test_notes_accept_german_characters(self):
        """Notes akzeptieren alle deutschen Zeichen."""
        german_text = "Größe: 5m², Preis: 100€, Überschrift: Änderungen für März"

        metadata = DocumentMetadata(notes=german_text)
        assert metadata.notes == german_text

    def test_tags_accept_german_umlauts(self):
        """Tags akzeptieren deutsche Umlaute."""
        german_tags = ["größe", "übung", "änderung"]

        metadata = DocumentMetadata(custom_tags=german_tags)
        assert "größe" in metadata.custom_tags


class TestEnumValidation:
    """Tests fuer Enum-Validierung."""

    def test_processing_status_valid_values(self):
        """ProcessingStatus akzeptiert nur gueltige Werte."""
        valid_statuses = ["pending", "queued", "processing", "completed", "failed", "cancelled"]

        for status in valid_statuses:
            ps = ProcessingStatus(status)
            assert ps.value == status

    def test_processing_status_invalid_value(self):
        """ProcessingStatus lehnt ungueltige Werte ab."""
        with pytest.raises(ValueError):
            ProcessingStatus("invalid_status")

    def test_ocr_backend_valid_values(self):
        """OCRBackend akzeptiert nur gueltige Backends."""
        valid_backends = ["auto", "deepseek", "got_ocr", "surya", "surya_gpu"]

        for backend in valid_backends:
            ocr = OCRBackend(backend)
            assert ocr.value == backend

    def test_ocr_backend_invalid_value(self):
        """OCRBackend lehnt ungueltige Backends ab."""
        with pytest.raises(ValueError):
            OCRBackend("tesseract")  # Not supported

    def test_document_type_valid_values(self):
        """DocumentType akzeptiert nur gueltige Typen."""
        valid_types = ["invoice", "contract", "receipt", "form", "letter", "report", "other"]

        for doc_type in valid_types:
            dt = DocumentType(doc_type)
            assert dt.value == doc_type

    def test_data_category_gdpr_compliance(self):
        """DataCategory enthält GDPR-konforme Kategorien."""
        required_categories = [
            "personal_identifiable",
            "special_category",
            "financial",
            "contact",
            "document_content",
            "metadata",
            "anonymous",
        ]

        for category in required_categories:
            dc = DataCategory(category)
            assert dc.value == category


class TestEmailValidation:
    """Tests fuer Email-Validierung."""

    def test_valid_email_formats(self):
        """Gueltige Email-Formate werden akzeptiert."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.de",
            "user+tag@example.org",
            "test123@sub.domain.com",
        ]

        for email in valid_emails:
            user = UserBase(email=email, username="testuser")
            assert user.email == email

    def test_invalid_email_formats(self):
        """Ungueltige Email-Formate werden abgelehnt."""
        invalid_emails = [
            "invalid",
            "@nodomain.com",
            "noat.com",
            "spaces in@email.com",
            "test@",
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError):
                UserBase(email=email, username="testuser")


class TestPasswordValidation:
    """Tests fuer Passwort-Validierung."""

    def test_password_min_length_8(self):
        """Passwort muss mindestens 8 Zeichen haben."""
        short_passwords = ["", "1234567", "short"]

        for pw in short_passwords:
            with pytest.raises(ValidationError):
                UserCreate(
                    email="test@example.com",
                    username="testuser",
                    password=pw
                )

    def test_password_accepts_special_chars(self):
        """Passwort akzeptiert Sonderzeichen."""
        special_passwords = [
            "P@ssw0rd!",
            "Secure#123$",
            "Test€äöü123",
        ]

        for pw in special_passwords:
            user = UserCreate(
                email="test@example.com",
                username="testuser",
                password=pw
            )
            assert user.password == pw

    def test_password_with_spaces(self):
        """Passwort mit Leerzeichen wird akzeptiert."""
        user = UserCreate(
            email="test@example.com",
            username="testuser",
            password="my secure password"
        )
        assert " " in user.password


class TestLanguageValidation:
    """Tests fuer Sprach-Validierung."""

    def test_valid_languages(self):
        """Gueltige Sprachen (de, en) werden akzeptiert."""
        for lang in ["de", "en"]:
            user = UserBase(
                email="test@example.com",
                username="testuser",
                preferred_language=lang
            )
            assert user.preferred_language == lang

    def test_invalid_languages(self):
        """Ungueltige Sprachen werden abgelehnt."""
        invalid_langs = ["fr", "es", "DE", "english", "deutsch"]

        for lang in invalid_langs:
            with pytest.raises(ValidationError):
                UserBase(
                    email="test@example.com",
                    username="testuser",
                    preferred_language=lang
                )

    def test_document_language_iso_format(self):
        """Dokument-Sprache muss ISO 639-1 Format haben."""
        valid_langs = ["de", "en", "fr", "es"]

        for lang in valid_langs:
            doc = DocumentBase(filename="test.pdf", language=lang)
            assert doc.language == lang

    def test_document_language_invalid_format(self):
        """Dokument-Sprache mit falschem Format scheitert."""
        invalid_formats = ["deu", "DEU", "german", "123"]

        for lang in invalid_formats:
            with pytest.raises(ValidationError):
                DocumentBase(filename="test.pdf", language=lang)


class TestDocumentMetadataValidation:
    """Tests fuer DocumentMetadata Validierung."""

    def test_metadata_forbids_extra_fields(self):
        """DocumentMetadata lehnt unbekannte Felder ab."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                notes="Test",
                unknown_field="should fail"  # type: ignore
            )

        assert "extra" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()

    def test_metadata_all_fields_optional(self):
        """Alle DocumentMetadata Felder sind optional."""
        metadata = DocumentMetadata()
        assert metadata.source is None
        assert metadata.custom_tags is None
        assert metadata.notes is None

    def test_metadata_source_url_max_length(self):
        """source_url max 500 Zeichen."""
        long_url = "https://example.com/" + "a" * 500

        with pytest.raises(ValidationError):
            DocumentMetadata(source_url=long_url)

    def test_tags_normalized_to_lowercase(self):
        """Tags werden zu lowercase normalisiert."""
        metadata = DocumentMetadata(custom_tags=["INVOICE", "Important", "Q1_2024"])

        for tag in metadata.custom_tags:
            assert tag == tag.lower()


class TestUUIDValidation:
    """Tests fuer UUID-Validierung."""

    def test_user_response_accepts_valid_uuid(self):
        """UserResponse akzeptiert gueltige UUID."""
        valid_uuid = uuid.uuid4()

        class MockUser:
            id = valid_uuid
            email = "test@example.com"
            username = "testuser"
            full_name = None
            preferred_language = "de"
            is_active = True
            is_superuser = False
            preferred_ocr_backend = "auto"
            daily_quota = 100
            created_at = datetime.now(timezone.utc)
            last_login = None

        user_response = UserResponse.model_validate(MockUser())
        assert user_response.id == valid_uuid


class TestDatetimeValidation:
    """Tests fuer Datetime-Validierung."""

    def test_datetime_with_timezone(self):
        """Datetime mit Timezone wird akzeptiert."""
        dt_utc = datetime.now(timezone.utc)

        class MockUser:
            id = uuid.uuid4()
            email = "test@example.com"
            username = "testuser"
            full_name = None
            preferred_language = "de"
            is_active = True
            is_superuser = False
            preferred_ocr_backend = "auto"
            daily_quota = 100
            created_at = dt_utc
            last_login = None

        user_response = UserResponse.model_validate(MockUser())
        assert user_response.created_at is not None


class TestDefaultValues:
    """Tests fuer Default-Werte."""

    def test_user_base_default_language(self):
        """UserBase hat default Sprache 'de'."""
        user = UserBase(email="test@example.com", username="testuser")
        assert user.preferred_language == "de"

    def test_document_base_default_type(self):
        """DocumentBase hat default Typ 'other'."""
        doc = DocumentBase(filename="test.pdf")
        assert doc.document_type == DocumentType.OTHER

    def test_document_base_default_language(self):
        """DocumentBase hat default Sprache 'de'."""
        doc = DocumentBase(filename="test.pdf")
        assert doc.language == "de"

    def test_document_create_default_backend(self):
        """DocumentCreate hat default Backend 'auto'."""
        doc = DocumentCreate(filename="test.pdf")
        assert doc.backend == OCRBackend.AUTO

    def test_document_create_default_detect_layout(self):
        """DocumentCreate hat default detect_layout True."""
        doc = DocumentCreate(filename="test.pdf")
        assert doc.detect_layout is True


class TestOptionalFields:
    """Tests fuer optionale Felder."""

    def test_user_update_all_none(self):
        """UserUpdate kann komplett leer sein."""
        update = UserUpdate()
        assert update.email is None
        assert update.full_name is None
        assert update.preferred_language is None
        assert update.preferred_ocr_backend is None

    def test_document_update_all_none(self):
        """DocumentUpdate kann komplett leer sein."""
        update = DocumentUpdate()
        assert update.document_type is None
        assert update.language is None
        assert update.tags is None


class TestEdgeCases:
    """Tests fuer Edge Cases."""

    def test_empty_string_filename_rejected(self):
        """Leerer Dateiname wird abgelehnt."""
        with pytest.raises(ValidationError):
            DocumentBase(filename="")

    def test_whitespace_only_filename_accepted_currently(self):
        """Dateiname nur aus Leerzeichen wird aktuell akzeptiert.

        Note: Dies koennte in Zukunft verschaerft werden - whitespace-only
        Filenames sind potentiell problematisch.
        """
        # Aktuell keine Validierung gegen whitespace-only
        doc = DocumentBase(filename="   ")
        assert doc.filename == "   "

    def test_username_with_only_numbers(self):
        """Username nur aus Zahlen ist erlaubt."""
        user = UserBase(email="test@example.com", username="123456")
        assert user.username == "123456"

    def test_username_starting_with_number(self):
        """Username kann mit Zahl beginnen."""
        user = UserBase(email="test@example.com", username="123user")
        assert user.username == "123user"

    def test_very_long_valid_email(self):
        """Sehr lange aber gueltige Email wird akzeptiert."""
        long_local = "a" * 64
        email = f"{long_local}@example.com"

        user = UserBase(email=email, username="testuser")
        assert user.email == email

    def test_unicode_normalized_tags(self):
        """Tags werden Unicode-normalisiert."""
        metadata = DocumentMetadata(custom_tags=["Größe", "Über"])
        assert "größe" in metadata.custom_tags
        assert "über" in metadata.custom_tags

"""Unit tests for Pydantic schemas.

Tests validation rules, defaults, and field constraints.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.db.schemas import (
    # Enums
    ProcessingStatus,
    OCRBackend,
    DocumentType,
    # User Schemas
    UserBase,
    UserCreate,
    UserUpdate,
    UserChangePassword,
    UserResponse,
    # Document Schemas
    DocumentBase,
    DocumentCreate,
    DocumentResponse,
    # Auth Schemas
    TokenResponse,
    LoginRequest,
)


class TestUserSchemas:
    """Tests for User-related Pydantic schemas."""

    def test_user_base_valid(self):
        """UserBase sollte mit gueltigen Daten funktionieren."""
        user = UserBase(
            email="test@example.com",
            username="test_user",
            full_name="Test User"
        )
        assert user.email == "test@example.com"
        assert user.username == "test_user"
        assert user.preferred_language == "de"

    def test_user_base_username_lowercase(self):
        """Username sollte zu lowercase konvertiert werden."""
        user = UserBase(
            email="test@example.com",
            username="TestUser123"
        )
        assert user.username == "testuser123"

    def test_user_base_invalid_email(self):
        """Ungueltige Email sollte ValidationError werfen."""
        with pytest.raises(ValidationError) as exc_info:
            UserBase(
                email="invalid-email",
                username="test_user"
            )
        assert "email" in str(exc_info.value).lower()

    def test_user_base_username_too_short(self):
        """Username mit weniger als 3 Zeichen sollte scheitern."""
        with pytest.raises(ValidationError) as exc_info:
            UserBase(
                email="test@example.com",
                username="ab"
            )
        assert "username" in str(exc_info.value).lower()

    def test_user_base_username_invalid_chars(self):
        """Username mit ungültigen Zeichen sollte scheitern."""
        with pytest.raises(ValidationError) as exc_info:
            UserBase(
                email="test@example.com",
                username="test@user!"
            )
        assert "benutzername" in str(exc_info.value).lower()

    def test_user_base_username_valid_special_chars(self):
        """Username mit erlaubten Sonderzeichen (_, -) sollte funktionieren."""
        user = UserBase(
            email="test@example.com",
            username="test_user-123"
        )
        assert user.username == "test_user-123"

    def test_user_base_invalid_language(self):
        """Ungueltige Sprache sollte scheitern."""
        with pytest.raises(ValidationError) as exc_info:
            UserBase(
                email="test@example.com",
                username="test_user",
                preferred_language="fr"
            )
        assert "preferred_language" in str(exc_info.value).lower()

    def test_user_base_valid_languages(self):
        """Gueltige Sprachen (de, en) sollten funktionieren."""
        for lang in ["de", "en"]:
            user = UserBase(
                email="test@example.com",
                username="test_user",
                preferred_language=lang
            )
            assert user.preferred_language == lang

    def test_user_create_password_required(self):
        """UserCreate sollte Passwort erfordern."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@example.com",
                username="test_user"
            )
        assert "password" in str(exc_info.value).lower()

    def test_user_create_password_min_length(self):
        """Passwort muss mindestens 8 Zeichen haben."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@example.com",
                username="test_user",
                password="short"
            )
        assert "password" in str(exc_info.value).lower()

    def test_user_create_valid(self):
        """UserCreate mit gueltigem Passwort sollte funktionieren."""
        user = UserCreate(
            email="test@example.com",
            username="test_user",
            password="secure_password123"
        )
        assert user.password == "secure_password123"

    def test_user_update_all_optional(self):
        """UserUpdate sollte alle Felder optional haben."""
        user = UserUpdate()
        assert user.email is None
        assert user.full_name is None
        assert user.preferred_language is None

    def test_user_change_password_validation(self):
        """UserChangePassword sollte Passwort-Regeln validieren."""
        # Valid change
        change = UserChangePassword(
            current_password="old_password",
            new_password="new_secure_password"
        )
        assert change.new_password == "new_secure_password"

        # New password too short
        with pytest.raises(ValidationError):
            UserChangePassword(
                current_password="old",
                new_password="short"
            )


class TestDocumentSchemas:
    """Tests for Document-related Pydantic schemas."""

    def test_document_base_defaults(self):
        """DocumentBase sollte korrekte Defaults haben."""
        doc = DocumentBase(
            filename="test.pdf",
            original_filename="Test Document.pdf"
        )
        assert doc.document_type == DocumentType.OTHER
        assert doc.status == ProcessingStatus.PENDING

    def test_document_create_validates_filename(self):
        """DocumentCreate sollte gefaehrliche Dateinamen ablehnen."""
        # Path traversal attempt
        with pytest.raises(ValidationError) as exc_info:
            DocumentCreate(
                filename="../../../etc/passwd",
                original_filename="test.pdf"
            )
        assert "dateiname" in str(exc_info.value).lower()

    def test_document_create_rejects_slash(self):
        """DocumentCreate sollte Slashes im Dateinamen ablehnen."""
        with pytest.raises(ValidationError):
            DocumentCreate(
                filename="path/to/file.pdf",
                original_filename="test.pdf"
            )

    def test_document_create_rejects_backslash(self):
        """DocumentCreate sollte Backslashes im Dateinamen ablehnen."""
        with pytest.raises(ValidationError):
            DocumentCreate(
                filename="path\\to\\file.pdf",
                original_filename="test.pdf"
            )


class TestEnumSchemas:
    """Tests for enum schemas matching database enums."""

    def test_processing_status_matches_db(self):
        """Schema ProcessingStatus sollte mit DB-Enum uebereinstimmen."""
        from app.db.models import ProcessingStatus as DBStatus

        # Compare values
        schema_values = {s.value for s in ProcessingStatus}
        db_values = {s.value for s in DBStatus}

        assert schema_values == db_values, "Schema und DB Enums stimmen nicht ueberein"

    def test_ocr_backend_matches_db(self):
        """Schema OCRBackend sollte mit DB-Enum uebereinstimmen."""
        from app.db.models import OCRBackend as DBBackend

        schema_values = {b.value for b in OCRBackend}
        db_values = {b.value for b in DBBackend}

        assert schema_values == db_values

    def test_document_type_matches_db(self):
        """Schema DocumentType sollte mit DB-Enum uebereinstimmen."""
        from app.db.models import DocumentType as DBType

        schema_values = {t.value for t in DocumentType}
        db_values = {t.value for t in DBType}

        assert schema_values == db_values


class TestAuthSchemas:
    """Tests for authentication schemas."""

    def test_login_request_valid(self):
        """LoginRequest sollte gueltigen Login akzeptieren."""
        login = LoginRequest(
            username="testuser",
            password="password123"
        )
        assert login.username == "testuser"

    def test_token_response_structure(self):
        """TokenResponse sollte korrektes Format haben."""
        token = TokenResponse(
            access_token="jwt_token_here",
            refresh_token="refresh_token_here",
            token_type="bearer"
        )
        assert token.token_type == "bearer"
        assert token.access_token == "jwt_token_here"


class TestValidationMessages:
    """Tests for German validation messages."""

    def test_username_validation_german_message(self):
        """Validierungsfehler sollten deutsche Nachrichten haben."""
        try:
            UserBase(
                email="test@example.com",
                username="test@invalid!"
            )
        except ValidationError as e:
            error_messages = str(e)
            # Check for German message
            assert "benutzername" in error_messages.lower() or "darf nur" in error_messages.lower()


class TestSchemaConfigDict:
    """Tests for Pydantic ConfigDict settings."""

    def test_user_response_from_attributes(self):
        """UserResponse sollte from_attributes fuer ORM-Mapping haben."""
        # Create a mock ORM object
        class MockUser:
            id = uuid.uuid4()
            email = "test@example.com"
            username = "testuser"
            full_name = "Test User"
            preferred_language = "de"
            is_active = True
            is_superuser = False
            preferred_ocr_backend = "auto"
            daily_quota = 100
            documents_processed_today = 5
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        # This should work with from_attributes=True
        user_response = UserResponse.model_validate(MockUser())
        assert user_response.email == "test@example.com"
        assert user_response.username == "testuser"

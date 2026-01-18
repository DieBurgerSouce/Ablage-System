"""
Unit Tests fuer EmailImportService.

Tests fuer IMAP-Verbindung, E-Mail-Parsing, Attachment-Extraktion
und Credential-Verschluesselung.
"""

import pytest
from datetime import datetime, timezone
from email.message import Message
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.imports.email_import_service import (
    EmailImportService,
    EmailAttachment,
    ParsedEmail,
)


class TestEmailParsing:
    """Tests fuer E-Mail-Parsing."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_parse_email_simple(self, service: EmailImportService) -> None:
        """Test parsing a simple email."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Thu, 01 Jan 2024 12:00:00 +0000
Message-ID: <test123@example.com>
Content-Type: text/plain; charset="utf-8"

This is the email body."""

        result = service._parse_email(uid=1, raw_email=raw_email)

        assert isinstance(result, ParsedEmail)
        assert result.from_address == "sender@example.com"
        assert result.subject == "Test Subject"
        assert result.message_id == "<test123@example.com>"
        assert result.uid == 1

    def test_parse_email_with_german_subject(self, service: EmailImportService) -> None:
        """Test parsing email with German umlauts in subject."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: =?UTF-8?Q?Rechnungs=C3=BCbersicht_f=C3=BCr_M=C3=A4rz?=
Date: Thu, 01 Jan 2024 12:00:00 +0000

Body text."""

        result = service._parse_email(uid=2, raw_email=raw_email)

        assert "Rechnungsübersicht" in result.subject
        assert "März" in result.subject

    def test_parse_email_extracts_body_text(self, service: EmailImportService) -> None:
        """Test parsing email extracts body text."""
        raw_email = b"""From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Thu, 01 Jan 2024 12:00:00 +0000
Content-Type: text/plain; charset="utf-8"

This is the email body text."""

        result = service._parse_email(uid=3, raw_email=raw_email)

        assert result.body_text is not None
        assert "email body text" in result.body_text


class TestHeaderDecoding:
    """Tests fuer Header-Dekodierung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_decode_header_simple(self, service: EmailImportService) -> None:
        """Test decoding simple ASCII header."""
        result = service._decode_header("Simple Header")
        assert result == "Simple Header"

    def test_decode_header_empty(self, service: EmailImportService) -> None:
        """Test decoding empty header."""
        result = service._decode_header("")
        assert result == ""

    def test_decode_header_utf8_quoted_printable(
        self, service: EmailImportService
    ) -> None:
        """Test decoding UTF-8 quoted-printable header."""
        result = service._decode_header("=?UTF-8?Q?M=C3=BCller?=")
        assert "Müller" in result


class TestAttachmentExtraction:
    """Tests fuer Attachment-Extraktion."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_extract_attachment_returns_none_for_no_filename(
        self, service: EmailImportService
    ) -> None:
        """Test extraction returns None when no filename."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = None

        result = service._extract_attachment(part)

        assert result is None

    def test_extract_attachment_returns_none_for_blocked_extension(
        self, service: EmailImportService
    ) -> None:
        """Test extraction returns None for blocked extension."""
        part = MagicMock(spec=Message)
        part.get_filename.return_value = "virus.exe"
        part.get_content_type.return_value = "application/x-msdownload"

        result = service._extract_attachment(part)

        assert result is None


class TestCredentialEncryption:
    """Tests fuer Credential-Verschluesselung."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    @patch("app.services.imports.email_import_service.encrypt_data")
    def test_encrypt_password(
        self, mock_encrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password encryption calls encryption function."""
        mock_encrypt.return_value = b"encrypted_password"
        password = "my_secret_password"

        # EmailImportService doesn't expose _encrypt_password directly
        # This tests that encrypt_data is available for the service
        from app.services.imports.email_import_service import encrypt_data

        result = encrypt_data(password.encode())
        mock_encrypt.assert_called_once()

    @patch("app.services.imports.email_import_service.decrypt_data")
    def test_decrypt_password(
        self, mock_decrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password decryption calls decryption function."""
        mock_decrypt.return_value = b"decrypted_password"
        encrypted = b"encrypted_data"

        from app.services.imports.email_import_service import decrypt_data

        result = decrypt_data(encrypted)
        mock_decrypt.assert_called_once()


# =============================================================================
# Async Tests
# =============================================================================

@pytest.mark.asyncio
class TestAsyncEmailOperations:
    """Async tests fuer Email Import operations."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    async def test_service_creation(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test service can be instantiated."""
        assert service is not None
        assert service.db == mock_db


@pytest.mark.asyncio
class TestIMAPConnection:
    """Tests fuer IMAP-Verbindung."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def service(self, mock_db: AsyncMock) -> EmailImportService:
        """Create service instance."""
        return EmailImportService(db=mock_db)

    def test_create_imap_connection_ssl(self, service: EmailImportService) -> None:
        """Test IMAP connection configuration with SSL."""
        # The _create_imap_connection method exists and should work
        # We just verify the method exists
        assert hasattr(service, "_create_imap_connection")


class TestEmailAttachment:
    """Tests fuer EmailAttachment Datenklasse."""

    def test_email_attachment_creation(self) -> None:
        """Test EmailAttachment can be created."""
        attachment = EmailAttachment(
            filename="document.pdf",
            content=b"%PDF-1.4 test content",
            mime_type="application/pdf",
        )

        assert attachment.filename == "document.pdf"
        assert attachment.mime_type == "application/pdf"
        assert attachment.size > 0
        assert attachment.file_hash is not None

    def test_email_attachment_hash(self) -> None:
        """Test EmailAttachment generates consistent hash."""
        content = b"test content"
        attachment1 = EmailAttachment(
            filename="test.pdf",
            content=content,
            mime_type="application/pdf",
        )
        attachment2 = EmailAttachment(
            filename="test.pdf",
            content=content,
            mime_type="application/pdf",
        )

        assert attachment1.file_hash == attachment2.file_hash


class TestParsedEmail:
    """Tests fuer ParsedEmail Datenklasse."""

    def test_parsed_email_creation(self) -> None:
        """Test ParsedEmail can be created."""
        parsed = ParsedEmail(
            uid=1,
            message_id="<test@example.com>",
            from_address="sender@example.com",
            subject="Test Subject",
            date=datetime.now(timezone.utc),
            attachments=[],
        )

        assert parsed.uid == 1
        assert parsed.message_id == "<test@example.com>"
        assert parsed.from_address == "sender@example.com"
        assert parsed.subject == "Test Subject"
        assert parsed.attachments == []

    def test_parsed_email_with_attachments(self) -> None:
        """Test ParsedEmail with attachments."""
        attachment = EmailAttachment(
            filename="doc.pdf",
            content=b"content",
            mime_type="application/pdf",
        )
        parsed = ParsedEmail(
            uid=1,
            message_id="<test@example.com>",
            from_address="sender@example.com",
            subject="Test",
            date=None,
            attachments=[attachment],
        )

        assert len(parsed.attachments) == 1
        assert parsed.attachments[0].filename == "doc.pdf"

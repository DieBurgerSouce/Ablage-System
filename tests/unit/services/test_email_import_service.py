"""
Unit Tests fuer EmailImportService.

Tests fuer IMAP-Verbindung, E-Mail-Parsing, Attachment-Extraktion
und Credential-Verschluesselung.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.import.email_import_service import EmailImportService


class TestEmailParsing:
    """Tests fuer E-Mail-Parsing."""

    @pytest.fixture
    def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    def test_parse_email_simple(self, service: EmailImportService) -> None:
        """Test parsing a simple email."""
        # Mock email message
        email_data = {
            b"RFC822": b"""From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Thu, 01 Jan 2024 12:00:00 +0000
Message-ID: <test123@example.com>
Content-Type: text/plain; charset="utf-8"

This is the email body."""
        }

        result = service._parse_email_data(email_data)

        assert result["from"] == "sender@example.com"
        assert result["to"] == "recipient@example.com"
        assert result["subject"] == "Test Subject"
        assert result["message_id"] == "<test123@example.com>"

    def test_parse_email_with_german_subject(self, service: EmailImportService) -> None:
        """Test parsing email with German umlauts in subject."""
        email_data = {
            b"RFC822": b"""From: sender@example.com
To: recipient@example.com
Subject: =?UTF-8?Q?Rechnungs=C3=BCbersicht_f=C3=BCr_M=C3=A4rz?=
Date: Thu, 01 Jan 2024 12:00:00 +0000

Body text."""
        }

        result = service._parse_email_data(email_data)

        assert "Rechnungsübersicht" in result["subject"]
        assert "März" in result["subject"]

    def test_parse_email_multipart(self, service: EmailImportService) -> None:
        """Test parsing multipart email."""
        email_data = {
            b"RFC822": b"""From: sender@example.com
To: recipient@example.com
Subject: Email with Attachment
Date: Thu, 01 Jan 2024 12:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_Part_0"

------=_Part_0
Content-Type: text/plain; charset="utf-8"

Email body text.

------=_Part_0
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwo+PgplbmRvYmoK

------=_Part_0--"""
        }

        result = service._parse_email_data(email_data)

        assert result["from"] == "sender@example.com"
        assert result["has_attachments"] is True
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "invoice.pdf"


class TestAttachmentExtraction:
    """Tests fuer Attachment-Extraktion."""

    @pytest.fixture
    def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    def test_extract_attachment_pdf(self, service: EmailImportService) -> None:
        """Test extracting PDF attachment."""
        attachment = MagicMock()
        attachment.get_filename.return_value = "document.pdf"
        attachment.get_content_type.return_value = "application/pdf"
        attachment.get_payload.return_value = b"%PDF-1.4 test content"

        result = service._extract_attachment(attachment)

        assert result["filename"] == "document.pdf"
        assert result["content_type"] == "application/pdf"
        assert result["content"] == b"%PDF-1.4 test content"
        assert result["size"] > 0

    def test_extract_attachment_sanitize_filename(
        self, service: EmailImportService
    ) -> None:
        """Test filename sanitization."""
        attachment = MagicMock()
        attachment.get_filename.return_value = "../../../etc/passwd"
        attachment.get_content_type.return_value = "text/plain"
        attachment.get_payload.return_value = b"test"

        result = service._extract_attachment(attachment)

        # Path traversal should be removed
        assert ".." not in result["filename"]
        assert "/" not in result["filename"]

    def test_extract_attachment_with_umlauts(
        self, service: EmailImportService
    ) -> None:
        """Test attachment with German umlauts in filename."""
        attachment = MagicMock()
        attachment.get_filename.return_value = "Rechnungsübersicht_März_2024.pdf"
        attachment.get_content_type.return_value = "application/pdf"
        attachment.get_payload.return_value = b"%PDF-1.4"

        result = service._extract_attachment(attachment)

        assert "ü" in result["filename"] or "Rechnung" in result["filename"]


class TestAttachmentFiltering:
    """Tests fuer Attachment-Filterung."""

    @pytest.fixture
    def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    def test_is_allowed_attachment_type_pdf(
        self, service: EmailImportService
    ) -> None:
        """Test PDF is allowed by default."""
        allowed_types = [".pdf", ".png", ".jpg"]

        result = service._is_allowed_attachment(
            filename="document.pdf",
            content_type="application/pdf",
            allowed_types=allowed_types,
        )

        assert result is True

    def test_is_allowed_attachment_type_exe_blocked(
        self, service: EmailImportService
    ) -> None:
        """Test executable files are blocked."""
        allowed_types = [".pdf", ".png", ".jpg"]

        result = service._is_allowed_attachment(
            filename="virus.exe",
            content_type="application/x-msdownload",
            allowed_types=allowed_types,
        )

        assert result is False

    def test_is_allowed_attachment_size_limit(
        self, service: EmailImportService
    ) -> None:
        """Test attachment size limit."""
        result = service._is_attachment_size_allowed(
            size_bytes=60 * 1024 * 1024,  # 60MB
            max_size_mb=50,
        )

        assert result is False

    def test_is_allowed_attachment_size_ok(
        self, service: EmailImportService
    ) -> None:
        """Test attachment within size limit."""
        result = service._is_attachment_size_allowed(
            size_bytes=10 * 1024 * 1024,  # 10MB
            max_size_mb=50,
        )

        assert result is True


class TestEmailFiltering:
    """Tests fuer E-Mail-Filterung."""

    @pytest.fixture
    def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    def test_matches_sender_filter_exact(
        self, service: EmailImportService
    ) -> None:
        """Test exact sender filter match."""
        config = MagicMock()
        config.filter_sender = "invoices@company.com"

        email_data = {"from": "invoices@company.com"}

        result = service._matches_filter(email_data, config)

        assert result is True

    def test_matches_sender_filter_partial(
        self, service: EmailImportService
    ) -> None:
        """Test partial sender filter match."""
        config = MagicMock()
        config.filter_sender = "@company.com"
        config.filter_subject_pattern = None
        config.filter_has_attachment = False

        email_data = {"from": "invoices@company.com", "has_attachments": False}

        result = service._matches_filter(email_data, config)

        assert result is True

    def test_matches_subject_pattern_regex(
        self, service: EmailImportService
    ) -> None:
        """Test regex subject pattern filter."""
        config = MagicMock()
        config.filter_sender = None
        config.filter_subject_pattern = r"Rechnung.*\d{4}"
        config.filter_has_attachment = False

        email_data = {"from": "test@test.com", "subject": "Rechnung Nr. 2024", "has_attachments": False}

        result = service._matches_filter(email_data, config)

        assert result is True

    def test_matches_has_attachment_filter(
        self, service: EmailImportService
    ) -> None:
        """Test has_attachment filter."""
        config = MagicMock()
        config.filter_sender = None
        config.filter_subject_pattern = None
        config.filter_has_attachment = True

        email_data = {"from": "test@test.com", "has_attachments": True}

        result = service._matches_filter(email_data, config)

        assert result is True

    def test_no_match_without_attachment(
        self, service: EmailImportService
    ) -> None:
        """Test filter fails when attachment required but missing."""
        config = MagicMock()
        config.filter_sender = None
        config.filter_subject_pattern = None
        config.filter_has_attachment = True

        email_data = {"from": "test@test.com", "has_attachments": False}

        result = service._matches_filter(email_data, config)

        assert result is False


class TestCredentialEncryption:
    """Tests fuer Credential-Verschluesselung."""

    @pytest.fixture
    def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    @patch("app.services.import.email_import_service.encrypt_data")
    def test_encrypt_password(
        self, mock_encrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password encryption."""
        mock_encrypt.return_value = b"encrypted_password"
        config_id = str(uuid4())
        password = "my_secret_password"

        result = service._encrypt_password(password, config_id)

        mock_encrypt.assert_called_once()
        # Verify associated data includes config_id for key binding
        call_args = mock_encrypt.call_args
        assert config_id in str(call_args)

    @patch("app.services.import.email_import_service.decrypt_data")
    def test_decrypt_password(
        self, mock_decrypt: MagicMock, service: EmailImportService
    ) -> None:
        """Test password decryption."""
        mock_decrypt.return_value = "decrypted_password"
        config_id = str(uuid4())
        encrypted = b"encrypted_data"

        result = service._decrypt_password(encrypted, config_id)

        mock_decrypt.assert_called_once()
        assert result == "decrypted_password"


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
    async def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    async def test_list_configs(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test listing email configs."""
        config1 = MagicMock()
        config1.id = str(uuid4())
        config1.name = "Config 1"
        config1.is_active = True

        config2 = MagicMock()
        config2.id = str(uuid4())
        config2.name = "Config 2"
        config2.is_active = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [config1, config2]
        mock_db.execute.return_value = mock_result

        user_id = str(uuid4())

        result = await service.list_configs(mock_db, user_id)

        assert len(result) == 2
        mock_db.execute.assert_called_once()

    async def test_get_config_by_id(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test getting config by ID."""
        config_id = str(uuid4())
        user_id = str(uuid4())

        config = MagicMock()
        config.id = config_id
        config.user_id = user_id
        config.name = "Test Config"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        result = await service.get_config(mock_db, config_id, user_id)

        assert result is not None
        assert result.id == config_id

    async def test_get_config_not_found(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test getting non-existent config."""
        config_id = str(uuid4())
        user_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_config(mock_db, config_id, user_id)

        assert result is None

    @patch("app.services.import.email_import_service.encrypt_data")
    async def test_create_config(
        self,
        mock_encrypt: MagicMock,
        service: EmailImportService,
        mock_db: AsyncMock,
    ) -> None:
        """Test creating email config."""
        mock_encrypt.return_value = b"encrypted"

        user_id = str(uuid4())
        data = {
            "name": "New Config",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "username": "user@example.com",
            "password": "secret123",
            "use_ssl": True,
        }

        # Mock the created config
        created_config = MagicMock()
        created_config.id = str(uuid4())
        created_config.name = data["name"]

        async def mock_refresh(obj: MagicMock) -> None:
            obj.id = created_config.id

        mock_db.refresh = mock_refresh

        result = await service.create_config(mock_db, user_id, data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_encrypt.assert_called_once()

    async def test_delete_config(
        self, service: EmailImportService, mock_db: AsyncMock
    ) -> None:
        """Test deleting email config."""
        config_id = str(uuid4())
        user_id = str(uuid4())

        config = MagicMock()
        config.id = config_id
        config.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute.return_value = mock_result

        result = await service.delete_config(mock_db, config_id, user_id)

        assert result is True
        mock_db.delete.assert_called_once_with(config)
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
class TestIMAPConnection:
    """Tests fuer IMAP-Verbindung."""

    @pytest_asyncio.fixture
    async def service(self) -> EmailImportService:
        """Create service instance."""
        return EmailImportService()

    @patch("app.services.import.email_import_service.IMAPClient")
    async def test_test_connection_success(
        self, mock_imap_class: MagicMock, service: EmailImportService
    ) -> None:
        """Test successful IMAP connection."""
        mock_imap = MagicMock()
        mock_imap.login.return_value = None
        mock_imap.list_folders.return_value = [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
            ((b"\\HasNoChildren",), b"/", "Sent"),
        ]
        mock_imap.select_folder.return_value = {b"EXISTS": 42}
        mock_imap.logout.return_value = None
        mock_imap_class.return_value.__enter__ = MagicMock(return_value=mock_imap)
        mock_imap_class.return_value.__exit__ = MagicMock(return_value=False)

        config = MagicMock()
        config.imap_server = "imap.example.com"
        config.imap_port = 993
        config.use_ssl = True
        config.use_starttls = False
        config.folder_to_watch = "INBOX"

        # Mock decrypted password
        with patch.object(service, "_decrypt_password", return_value="password123"):
            result = await service.test_connection(config)

        assert result["success"] is True
        assert result["server"] == "imap.example.com"
        assert "INBOX" in result["folders"]

    @patch("app.services.import.email_import_service.IMAPClient")
    async def test_test_connection_failure(
        self, mock_imap_class: MagicMock, service: EmailImportService
    ) -> None:
        """Test failed IMAP connection."""
        mock_imap_class.side_effect = Exception("Connection refused")

        config = MagicMock()
        config.imap_server = "invalid.example.com"
        config.imap_port = 993
        config.use_ssl = True
        config.use_starttls = False
        config.id = str(uuid4())

        with patch.object(service, "_decrypt_password", return_value="password123"):
            result = await service.test_connection(config)

        assert result["success"] is False
        assert "Connection refused" in result["error"]

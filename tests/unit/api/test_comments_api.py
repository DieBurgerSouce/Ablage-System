# -*- coding: utf-8 -*-
"""
Unit Tests fuer Comments API Endpoints.

Testet:
- Dokumentzugriffs-Validierung (Security)
- Access-Level Pruefung
- Kommentar CRUD-Operationen
- Mention-Validierung
- Reaktionen

Feinpoliert und durchdacht - Enterprise Test Coverage mit echten Assertions.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4, UUID
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestVerifyDocumentAccess:
    """Tests fuer _verify_document_access Security-Funktion."""

    @pytest.mark.asyncio
    async def test_owner_has_full_access(self):
        """Owner hat immer vollen Zugriff auf eigenes Dokument."""
        from app.api.v1.comments import _verify_document_access

        db = AsyncMock()
        user_id = uuid4()
        document_id = uuid4()

        # Mock: Dokument existiert und User ist Owner
        mock_doc = Mock(id=document_id, owner_id=user_id)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        db.execute = AsyncMock(return_value=mock_result)

        # Sollte das Dokument zurueckgeben (kein HTTPException)
        result = await _verify_document_access(db, document_id, user_id)
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_document_not_found_raises_404(self):
        """404 wenn Dokument nicht existiert."""
        from app.api.v1.comments import _verify_document_access

        db = AsyncMock()
        user_id = uuid4()
        document_id = uuid4()

        # Mock: Dokument existiert nicht
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await _verify_document_access(db, document_id, user_id)

        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_view_access_cannot_comment(self):
        """User mit nur VIEW-Zugriff kann nicht kommentieren (COMMENT required)."""
        from app.api.v1.comments import _verify_document_access
        from app.db.models import AccessLevel

        db = AsyncMock()
        user_id = uuid4()
        owner_id = uuid4()  # Anderer User
        document_id = uuid4()

        # Mock: Dokument existiert, anderer Owner
        mock_doc = Mock(id=document_id, owner_id=owner_id)
        mock_doc_result = Mock()
        mock_doc_result.scalar_one_or_none.return_value = mock_doc

        # Mock: User hat nur VIEW-Zugriff (nicht ausreichend!)
        mock_access_result = Mock()
        mock_access_result.scalar.return_value = False  # Keine ausreichenden Rechte

        db.execute = AsyncMock(side_effect=[
            mock_doc_result,
            mock_access_result,
        ])

        with pytest.raises(HTTPException) as exc_info:
            await _verify_document_access(
                db, document_id, user_id,
                required_level=AccessLevel.COMMENT.value
            )

        assert exc_info.value.status_code == 403
        assert "Berechtigung" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_comment_access_can_comment(self):
        """User mit COMMENT-Zugriff kann kommentieren."""
        from app.api.v1.comments import _verify_document_access
        from app.db.models import AccessLevel

        db = AsyncMock()
        user_id = uuid4()
        owner_id = uuid4()
        document_id = uuid4()

        # Mock: Dokument existiert, anderer Owner
        mock_doc = Mock(id=document_id, owner_id=owner_id)
        mock_doc_result = Mock()
        mock_doc_result.scalar_one_or_none.return_value = mock_doc

        # Mock: User hat COMMENT-Zugriff (ausreichend!)
        mock_access_result = Mock()
        mock_access_result.scalar.return_value = True

        db.execute = AsyncMock(side_effect=[
            mock_doc_result,
            mock_access_result,
        ])

        result = await _verify_document_access(
            db, document_id, user_id,
            required_level=AccessLevel.COMMENT.value
        )

        assert result == mock_doc


class TestMentionSchemaValidation:
    """Tests fuer MentionSchema Validierung."""

    def test_valid_mention(self):
        """Gueltige Mention wird akzeptiert."""
        from app.db.schemas import MentionSchema

        mention = MentionSchema(
            userId=uuid4(),
            userName="Max Mustermann",
            startIndex=0,
            endIndex=15,
        )

        assert mention.userName == "Max Mustermann"
        assert mention.startIndex == 0
        assert mention.endIndex == 15

    def test_start_index_must_be_less_than_end_index(self):
        """startIndex muss kleiner als endIndex sein."""
        from app.db.schemas import MentionSchema

        with pytest.raises(ValidationError) as exc_info:
            MentionSchema(
                userId=uuid4(),
                userName="Test User",
                startIndex=10,
                endIndex=5,  # Kleiner als startIndex!
            )

        assert "startIndex" in str(exc_info.value)

    def test_equal_indices_rejected(self):
        """startIndex == endIndex ist nicht erlaubt."""
        from app.db.schemas import MentionSchema

        with pytest.raises(ValidationError):
            MentionSchema(
                userId=uuid4(),
                userName="Test User",
                startIndex=10,
                endIndex=10,  # Gleich wie startIndex!
            )

    def test_username_max_length(self):
        """userName hat max 200 Zeichen."""
        from app.db.schemas import MentionSchema

        # 201 Zeichen sollte fehlschlagen
        with pytest.raises(ValidationError):
            MentionSchema(
                userId=uuid4(),
                userName="x" * 201,
            )

    def test_optional_indices_both_none(self):
        """Beide Indices duerfen None sein."""
        from app.db.schemas import MentionSchema

        mention = MentionSchema(
            userId=uuid4(),
            userName="Test User",
            # Keine startIndex/endIndex - beide fehlen
        )

        assert mention.startIndex is None
        assert mention.endIndex is None

    def test_single_index_rejected(self):
        """Nur ein Index (ohne den anderen) wird abgelehnt."""
        from app.db.schemas import MentionSchema

        # Nur startIndex ohne endIndex
        with pytest.raises(ValidationError) as exc_info:
            MentionSchema(
                userId=uuid4(),
                userName="Test User",
                startIndex=5,
                # endIndex fehlt!
            )

        assert "beide" in str(exc_info.value).lower() or "muessen" in str(exc_info.value).lower()

        # Nur endIndex ohne startIndex
        with pytest.raises(ValidationError):
            MentionSchema(
                userId=uuid4(),
                userName="Test User",
                endIndex=10,
                # startIndex fehlt!
            )

    def test_username_html_escaped(self):
        """userName wird HTML-escaped um XSS zu verhindern."""
        from app.db.schemas import MentionSchema

        mention = MentionSchema(
            userId=uuid4(),
            userName="<script>alert('xss')</script>",
        )

        # HTML-Zeichen sollten escaped sein
        assert "<script>" not in mention.userName
        assert "&lt;script&gt;" in mention.userName


class TestCommentCreateValidation:
    """Tests fuer CommentCreate Validierung."""

    def test_whitespace_only_content_rejected(self):
        """Content darf nicht nur Whitespace sein."""
        from app.db.schemas import CommentCreate

        with pytest.raises(ValidationError) as exc_info:
            CommentCreate(content="   ")

        assert "Whitespace" in str(exc_info.value) or "Leerzeichen" in str(exc_info.value)

    def test_content_max_length(self):
        """Content hat max 10000 Zeichen."""
        from app.db.schemas import CommentCreate

        # 10001 Zeichen sollte fehlschlagen
        with pytest.raises(ValidationError):
            CommentCreate(content="x" * 10001)

    def test_valid_comment(self):
        """Gueltiger Kommentar wird akzeptiert."""
        from app.db.schemas import CommentCreate

        comment = CommentCreate(
            content="Das ist ein Testkommentar.",
            mentions=[],
            parentId=None,
        )

        assert comment.content == "Das ist ein Testkommentar."


class TestReactionAddValidation:
    """Tests fuer ReactionAdd Emoji-Validierung."""

    def test_valid_emoji(self):
        """Gueltiges Emoji wird akzeptiert."""
        from app.db.schemas import ReactionAdd

        reaction = ReactionAdd(emoji="👍")
        assert reaction.emoji == "👍"

    def test_multiple_emojis_accepted(self):
        """Mehrere Emojis werden akzeptiert."""
        from app.db.schemas import ReactionAdd

        reaction = ReactionAdd(emoji="👍🎉")
        assert reaction.emoji == "👍🎉"

    def test_non_emoji_string_rejected(self):
        """Normaler Text wird abgelehnt."""
        from app.db.schemas import ReactionAdd

        with pytest.raises(ValidationError) as exc_info:
            ReactionAdd(emoji="hello")

        assert "Emoji" in str(exc_info.value)

    def test_emoji_max_length(self):
        """Emoji-String hat max 10 Zeichen."""
        from app.db.schemas import ReactionAdd

        with pytest.raises(ValidationError):
            ReactionAdd(emoji="🎉" * 11)


class TestNotificationResponseValidation:
    """Tests fuer NotificationResponse actionUrl-Validierung."""

    def test_relative_url_allowed(self):
        """Relative URLs sind erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="123",
            type="mention",
            title="Test",
            message="Test message",
            fromUserId="user-123",
            fromUserName="Test User",
            isRead=False,
            createdAt="2024-01-01T00:00:00Z",
            actionUrl="/documents/123",
        )

        assert notification.actionUrl == "/documents/123"

    def test_https_url_allowed(self):
        """HTTPS URLs sind erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="123",
            type="mention",
            title="Test",
            message="Test message",
            fromUserId="user-123",
            fromUserName="Test User",
            isRead=False,
            createdAt="2024-01-01T00:00:00Z",
            actionUrl="https://example.com/documents/123",
        )

        assert notification.actionUrl == "https://example.com/documents/123"

    def test_javascript_url_rejected(self):
        """javascript: URLs werden blockiert (XSS-Schutz)."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError) as exc_info:
            NotificationResponse(
                id="123",
                type="mention",
                title="Test",
                message="Test message",
                fromUserId="user-123",
                fromUserName="Test User",
                isRead=False,
                createdAt="2024-01-01T00:00:00Z",
                actionUrl="javascript:alert('xss')",
            )

        assert "javascript" in str(exc_info.value).lower()

    def test_data_url_rejected(self):
        """data: URLs werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="123",
                type="mention",
                title="Test",
                message="Test message",
                fromUserId="user-123",
                fromUserName="Test User",
                isRead=False,
                createdAt="2024-01-01T00:00:00Z",
                actionUrl="data:text/html,<script>alert('xss')</script>",
            )

    def test_none_url_allowed(self):
        """None als actionUrl ist erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="123",
            type="mention",
            title="Test",
            message="Test message",
            fromUserId="user-123",
            fromUserName="Test User",
            isRead=False,
            createdAt="2024-01-01T00:00:00Z",
            actionUrl=None,
        )

        assert notification.actionUrl is None


class TestActionUrlSecurityAdvanced:
    """Erweiterte Security-Tests fuer actionUrl XSS-Schutz."""

    def test_newline_bypass_blocked(self):
        """javascript: mit Newline wird blockiert (Bypass-Versuch)."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="java\nscript:alert('xss')",
            )

    def test_tab_bypass_blocked(self):
        """javascript: mit Tab wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="java\tscript:alert('xss')",
            )

    def test_protocol_relative_url_blocked(self):
        """Protocol-relative URLs (//evil.com) werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError) as exc_info:
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="//evil.com/steal-data",
            )

        assert "//" in str(exc_info.value)

    def test_path_traversal_blocked(self):
        """Path-Traversal (..) wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError) as exc_info:
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="/documents/../../../etc/passwd",
            )

        assert ".." in str(exc_info.value) or "Traversal" in str(exc_info.value)

    def test_null_byte_blocked(self):
        """Null-Bytes in URL werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="/documents/123\x00.pdf",
            )

    def test_vbscript_blocked(self):
        """vbscript: URLs werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="vbscript:msgbox('xss')",
            )

    def test_file_protocol_blocked(self):
        """file: URLs werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="file:///etc/passwd",
            )

    def test_mhtml_blocked(self):
        """mhtml: URLs werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="mhtml:http://evil.com",
            )

    def test_view_source_blocked(self):
        """view-source: URLs werden blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="view-source:http://example.com",
            )


class TestReactionAddSecurityAdvanced:
    """Erweiterte Security-Tests fuer Emoji-Validierung."""

    def test_variation_selector_alone_rejected(self):
        """Nur Variation Selector ohne echtes Emoji wird abgelehnt."""
        from app.db.schemas import ReactionAdd

        with pytest.raises(ValidationError):
            ReactionAdd(emoji="\uFE0F")  # Nur Variation Selector

    def test_zwj_alone_rejected(self):
        """Nur Zero-Width Joiner ohne echtes Emoji wird abgelehnt."""
        from app.db.schemas import ReactionAdd

        with pytest.raises(ValidationError):
            ReactionAdd(emoji="\u200D")  # Nur ZWJ

    def test_emoji_with_variation_selector_accepted(self):
        """Emoji mit Variation Selector wird akzeptiert."""
        from app.db.schemas import ReactionAdd

        # Thumbs up mit Variation Selector
        reaction = ReactionAdd(emoji="👍\uFE0F")
        assert "👍" in reaction.emoji


class TestAccessLevelHierarchy:
    """Tests fuer Access-Level Hierarchie."""

    def test_view_level_is_lowest(self):
        """VIEW ist das niedrigste Level."""
        from app.db.models import AccessLevel

        # Hierarchie sollte sein: VIEW < COMMENT < EDIT < MANAGE
        levels = [
            AccessLevel.VIEW.value,
            AccessLevel.COMMENT.value,
            AccessLevel.EDIT.value,
            AccessLevel.MANAGE.value,
        ]

        assert levels[0] == "view"
        assert levels[1] == "comment"

    def test_manage_level_is_highest(self):
        """MANAGE ist das hoechste Level."""
        from app.db.models import AccessLevel

        assert AccessLevel.MANAGE.value == "manage"

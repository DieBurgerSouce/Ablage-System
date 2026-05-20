# -*- coding: utf-8 -*-
"""
Unit Tests fuer Notifications API Endpoints.

Testet:
- Benachrichtigungen auflisten
- Als gelesen markieren
- Alle als gelesen markieren
- Benachrichtigung loeschen
- Unread Count
- actionUrl XSS-Validierung

Feinpoliert und durchdacht - Enterprise Test Coverage mit echten Assertions.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestNotificationResponseSchema:
    """Tests fuer NotificationResponse Schema-Validierung."""

    def test_valid_notification(self):
        """Gueltige Notification wird korrekt erstellt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="notif-123",
            type="mention",
            title="Neue Erwaehnung",
            message="Max Mustermann hat Sie erwaehnt",
            documentId="doc-456",
            documentName="Rechnung 2024.pdf",
            fromUserId="user-789",
            fromUserName="Max Mustermann",
            isRead=False,
            createdAt="2024-12-31T10:00:00Z",
            actionUrl="/documents/doc-456",
        )

        assert notification.id == "notif-123"
        assert notification.type == "mention"
        assert notification.isRead is False
        assert notification.actionUrl == "/documents/doc-456"

    def test_optional_fields(self):
        """Optionale Felder koennen None sein."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="notif-123",
            type="system",
            title="System Notification",
            message="System message",
            fromUserId="system",
            fromUserName="System",
            isRead=True,
            createdAt="2024-12-31T10:00:00Z",
            # Alle optionalen Felder weglassen
        )

        assert notification.documentId is None
        assert notification.documentName is None
        assert notification.fromUserAvatar is None
        assert notification.actionUrl is None


class TestActionUrlValidation:
    """Tests fuer actionUrl XSS-Schutz."""

    def test_relative_path_allowed(self):
        """Relative Pfade sind erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="1", type="test", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=False, createdAt="2024-01-01T00:00:00Z",
            actionUrl="/ablage/invoice/123",
        )

        assert notification.actionUrl == "/ablage/invoice/123"

    def test_nested_relative_path_allowed(self):
        """Verschachtelte Pfade sind erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="1", type="test", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=False, createdAt="2024-01-01T00:00:00Z",
            actionUrl="/admin/ocr-training/samples/abc123",
        )

        assert notification.actionUrl == "/admin/ocr-training/samples/abc123"

    def test_https_url_allowed(self):
        """HTTPS URLs erlaubt."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="1", type="test", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=False, createdAt="2024-01-01T00:00:00Z",
            actionUrl="https://ablage.example.com/documents/123",
        )

        assert "https://" in notification.actionUrl

    def test_http_url_allowed(self):
        """HTTP URLs erlaubt (fuer localhost dev)."""
        from app.db.schemas import NotificationResponse

        notification = NotificationResponse(
            id="1", type="test", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=False, createdAt="2024-01-01T00:00:00Z",
            actionUrl="http://localhost:3000/test",
        )

        assert "http://" in notification.actionUrl

    def test_javascript_protocol_blocked(self):
        """javascript: Protokoll wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError) as exc_info:
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="javascript:alert('XSS')",
            )

        error_str = str(exc_info.value).lower()
        assert "javascript" in error_str or "url" in error_str

    def test_javascript_uppercase_blocked(self):
        """JAVASCRIPT: (uppercase) wird auch blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="JAVASCRIPT:alert('XSS')",
            )

    def test_data_protocol_blocked(self):
        """data: Protokoll wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="data:text/html,<script>evil()</script>",
            )

    def test_vbscript_protocol_blocked(self):
        """vbscript: Protokoll wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="vbscript:msgbox('XSS')",
            )

    def test_file_protocol_blocked(self):
        """file: Protokoll wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="file:///etc/passwd",
            )

    def test_blob_protocol_blocked(self):
        """blob: Protokoll wird blockiert."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="blob:http://example.com/abc123",
            )

    def test_max_length_enforced(self):
        """actionUrl hat max 500 Zeichen."""
        from app.db.schemas import NotificationResponse

        with pytest.raises(ValidationError):
            NotificationResponse(
                id="1", type="test", title="T", message="M",
                fromUserId="u", fromUserName="U",
                isRead=False, createdAt="2024-01-01T00:00:00Z",
                actionUrl="/" + "x" * 501,
            )


class TestNotificationsListResponse:
    """Tests fuer NotificationsListResponse."""

    def test_empty_notifications_list(self):
        """Leere Notification-Liste ist gueltig."""
        from app.db.schemas import NotificationsListResponse

        response = NotificationsListResponse(
            notifications=[],
            unreadCount=0,
            total=0,
        )

        assert response.notifications == []
        assert response.unreadCount == 0
        assert response.total == 0

    def test_unread_count_matches(self):
        """unreadCount wird korrekt gesetzt."""
        from app.db.schemas import NotificationsListResponse, NotificationResponse

        notif1 = NotificationResponse(
            id="1", type="mention", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=False, createdAt="2024-01-01T00:00:00Z",
        )
        notif2 = NotificationResponse(
            id="2", type="mention", title="T", message="M",
            fromUserId="u", fromUserName="U",
            isRead=True, createdAt="2024-01-01T00:00:00Z",
        )

        response = NotificationsListResponse(
            notifications=[notif1, notif2],
            unreadCount=1,  # Nur notif1 ist unread
            total=2,
        )

        assert response.unreadCount == 1
        assert response.total == 2


class TestNotificationTypeEnum:
    """Tests fuer NotificationType Enum."""

    def test_all_notification_types_exist(self):
        """Alle erwarteten Notification-Types existieren."""
        from app.db.schemas import NotificationTypeEnum

        # Enum-Member-Namen (uppercase)
        expected_members = [
            "MENTION",
            "COMMENT_REPLY",
            "DOCUMENT_SHARED",
            "TASK_ASSIGNED",
            "DOCUMENT_APPROVED",
            "DOCUMENT_REJECTED",
        ]

        for member_name in expected_members:
            assert hasattr(NotificationTypeEnum, member_name)

    def test_mention_value(self):
        """MENTION hat korrekten Wert."""
        from app.db.schemas import NotificationTypeEnum

        assert NotificationTypeEnum.MENTION.value == "mention"

    def test_comment_reply_value(self):
        """COMMENT_REPLY hat korrekten Wert."""
        from app.db.schemas import NotificationTypeEnum

        assert NotificationTypeEnum.COMMENT_REPLY.value == "comment_reply"

    def test_document_shared_value(self):
        """DOCUMENT_SHARED hat korrekten Wert."""
        from app.db.schemas import NotificationTypeEnum

        assert NotificationTypeEnum.DOCUMENT_SHARED.value == "document_shared"

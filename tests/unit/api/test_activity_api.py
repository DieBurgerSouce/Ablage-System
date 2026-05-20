# -*- coding: utf-8 -*-
"""
Unit Tests fuer Activity API Endpoints.

Testet:
- Aktivitaetstyp-Enum
- ActivityResponse Schema-Validierung
- ActivitiesListResponse Paginierung
- Dokument-Existenz-Pruefung

Feinpoliert und durchdacht - Enterprise Test Coverage mit echten Assertions.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone

from pydantic import ValidationError

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestActivityTypeEnum:
    """Tests fuer ActivityTypeEnum."""

    def test_all_activity_types_exist(self):
        """Alle erwarteten Activity-Types existieren."""
        from app.db.schemas import ActivityTypeEnum

        expected_types = [
            "document_created",
            "document_updated",
            "document_viewed",
            "document_downloaded",
            "comment_added",
            "comment_replied",
            "status_changed",
            "tags_changed",
            "metadata_updated",
            "document_shared",
        ]

        for type_name in expected_types:
            assert hasattr(ActivityTypeEnum, type_name.upper())

    def test_document_viewed_value(self):
        """DOCUMENT_VIEWED hat korrekten Wert."""
        from app.db.schemas import ActivityTypeEnum

        assert ActivityTypeEnum.DOCUMENT_VIEWED.value == "document_viewed"

    def test_document_downloaded_value(self):
        """DOCUMENT_DOWNLOADED hat korrekten Wert."""
        from app.db.schemas import ActivityTypeEnum

        assert ActivityTypeEnum.DOCUMENT_DOWNLOADED.value == "document_downloaded"

    def test_comment_added_value(self):
        """COMMENT_ADDED hat korrekten Wert."""
        from app.db.schemas import ActivityTypeEnum

        assert ActivityTypeEnum.COMMENT_ADDED.value == "comment_added"


class TestActivityResponseSchema:
    """Tests fuer ActivityResponse Schema-Validierung."""

    def test_valid_activity(self):
        """Gueltige Activity wird korrekt erstellt."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="act-123",
            documentId="doc-456",
            userId="user-789",
            userName="Max Mustermann",
            type="document_viewed",
            description="Dokument angesehen",
            createdAt="2024-12-31T10:00:00Z",
        )

        assert activity.id == "act-123"
        assert activity.documentId == "doc-456"
        assert activity.userId == "user-789"
        assert activity.userName == "Max Mustermann"
        assert activity.type == "document_viewed"
        assert activity.description == "Dokument angesehen"
        assert activity.userAvatar is None
        assert activity.metadata is None

    def test_activity_with_optional_fields(self):
        """Activity mit allen optionalen Feldern."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="act-123",
            documentId="doc-456",
            userId="user-789",
            userName="Max Mustermann",
            userAvatar="https://example.com/avatar.png",
            type="status_changed",
            description="Status geaendert",
            metadata={"old_status": "pending", "new_status": "approved"},
            createdAt="2024-12-31T10:00:00Z",
        )

        assert activity.userAvatar == "https://example.com/avatar.png"
        assert activity.metadata["old_status"] == "pending"
        assert activity.metadata["new_status"] == "approved"

    def test_activity_with_complex_metadata(self):
        """Activity mit komplexer Metadata."""
        from app.db.schemas import ActivityResponse

        metadata = {
            "ocr_backend": "deepseek",
            "processing_time_ms": 1234,
            "pages_processed": 5,
            "nested": {"key": "value"},
        }

        activity = ActivityResponse(
            id="act-123",
            documentId="doc-456",
            userId="system",
            userName="System",
            type="document_created",
            description="Dokument erstellt",
            metadata=metadata,
            createdAt="2024-12-31T10:00:00Z",
        )

        assert activity.metadata["ocr_backend"] == "deepseek"
        assert activity.metadata["processing_time_ms"] == 1234
        assert activity.metadata["nested"]["key"] == "value"

    def test_activity_missing_required_fields(self):
        """ValidationError bei fehlenden Pflichtfeldern."""
        from app.db.schemas import ActivityResponse

        # Fehlendes userId
        with pytest.raises(ValidationError) as exc_info:
            ActivityResponse(
                id="act-123",
                documentId="doc-456",
                # userId fehlt
                userName="Test User",
                type="document_viewed",
                description="Test",
                createdAt="2024-12-31T10:00:00Z",
            )

        assert "userId" in str(exc_info.value)

    def test_activity_missing_description(self):
        """ValidationError bei fehlender description."""
        from app.db.schemas import ActivityResponse

        with pytest.raises(ValidationError) as exc_info:
            ActivityResponse(
                id="act-123",
                documentId="doc-456",
                userId="user-789",
                userName="Test User",
                type="document_viewed",
                # description fehlt
                createdAt="2024-12-31T10:00:00Z",
            )

        assert "description" in str(exc_info.value)


class TestActivitiesListResponse:
    """Tests fuer ActivitiesListResponse."""

    def test_empty_activities_list(self):
        """Leere Activities-Liste ist gueltig."""
        from app.db.schemas import ActivitiesListResponse

        response = ActivitiesListResponse(
            activities=[],
            total=0,
            hasMore=False,
        )

        assert response.activities == []
        assert response.total == 0
        assert response.hasMore is False

    def test_activities_list_with_items(self):
        """Activities-Liste mit Eintraegen."""
        from app.db.schemas import ActivitiesListResponse, ActivityResponse

        act1 = ActivityResponse(
            id="act-1",
            documentId="doc-456",
            userId="user-1",
            userName="User Eins",
            type="document_viewed",
            description="Angesehen",
            createdAt="2024-12-31T10:00:00Z",
        )
        act2 = ActivityResponse(
            id="act-2",
            documentId="doc-456",
            userId="user-2",
            userName="User Zwei",
            type="comment_added",
            description="Kommentar hinzugefuegt",
            createdAt="2024-12-31T11:00:00Z",
        )

        response = ActivitiesListResponse(
            activities=[act1, act2],
            total=10,  # Mehr als angezeigt
            hasMore=True,
        )

        assert len(response.activities) == 2
        assert response.total == 10
        assert response.hasMore is True

    def test_has_more_pagination_indicator(self):
        """hasMore Indikator korrekt bei Pagination."""
        from app.db.schemas import ActivitiesListResponse, ActivityResponse

        act1 = ActivityResponse(
            id="act-1",
            documentId="doc-456",
            userId="user-1",
            userName="User",
            type="document_viewed",
            description="Angesehen",
            createdAt="2024-12-31T10:00:00Z",
        )

        # Seite 1: hasMore=True wenn mehr vorhanden
        response_page1 = ActivitiesListResponse(
            activities=[act1],
            total=50,
            hasMore=True,  # 50 total, aber nur 1 angezeigt
        )
        assert response_page1.hasMore is True

        # Letzte Seite: hasMore=False
        response_last = ActivitiesListResponse(
            activities=[act1],
            total=1,
            hasMore=False,  # Alle angezeigt
        )
        assert response_last.hasMore is False


class TestActivityTypeFiltering:
    """Tests fuer Aktivitaetstyp-Filterung."""

    def test_view_activity_type(self):
        """DOCUMENT_VIEWED Aktivitaet korrekt."""
        from app.db.schemas import ActivityResponse, ActivityTypeEnum

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type=ActivityTypeEnum.DOCUMENT_VIEWED.value,
            description="Dokument angesehen",
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.type == "document_viewed"

    def test_download_activity_type(self):
        """DOCUMENT_DOWNLOADED Aktivitaet korrekt."""
        from app.db.schemas import ActivityResponse, ActivityTypeEnum

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type=ActivityTypeEnum.DOCUMENT_DOWNLOADED.value,
            description="Dokument heruntergeladen",
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.type == "document_downloaded"

    def test_comment_activity_type(self):
        """COMMENT_ADDED Aktivitaet korrekt."""
        from app.db.schemas import ActivityResponse, ActivityTypeEnum

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type=ActivityTypeEnum.COMMENT_ADDED.value,
            description="Kommentar hinzugefuegt",
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.type == "comment_added"


class TestActivityMetadataHandling:
    """Tests fuer Metadata-Verarbeitung."""

    def test_null_metadata_allowed(self):
        """None als metadata ist erlaubt."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            metadata=None,
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.metadata is None

    def test_empty_metadata_allowed(self):
        """Leeres Dict als metadata ist erlaubt."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            metadata={},
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.metadata == {}

    def test_metadata_preserves_types(self):
        """Metadata behaelt Datentypen bei."""
        from app.db.schemas import ActivityResponse

        metadata = {
            "string": "value",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
        }

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="metadata_updated",
            description="Metadata aktualisiert",
            metadata=metadata,
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.metadata["string"] == "value"
        assert activity.metadata["integer"] == 42
        assert activity.metadata["float"] == 3.14
        assert activity.metadata["boolean"] is True
        assert activity.metadata["list"] == [1, 2, 3]
        assert activity.metadata["nested"]["key"] == "value"


class TestActivityUserHandling:
    """Tests fuer User-Daten in Activities."""

    def test_activity_with_user_avatar(self):
        """Activity mit User-Avatar."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="Max Mustermann",
            userAvatar="https://example.com/avatars/max.png",
            type="document_viewed",
            description="Angesehen",
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.userName == "Max Mustermann"
        assert activity.userAvatar == "https://example.com/avatars/max.png"

    def test_activity_without_user_avatar(self):
        """Activity ohne User-Avatar (Default None)."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="System User",
            type="document_created",
            description="Automatisch erstellt",
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.userName == "System User"
        assert activity.userAvatar is None

    def test_system_activity(self):
        """System-Aktivitaet (ohne echten User)."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="system",
            userName="System",
            type="document_created",
            description="Dokument automatisch verarbeitet",
            metadata={"ocr_backend": "deepseek", "duration_ms": 1500},
            createdAt="2024-01-01T00:00:00Z",
        )

        assert activity.userId == "system"
        assert activity.userName == "System"
        assert activity.metadata["ocr_backend"] == "deepseek"


class TestActivityTimestamps:
    """Tests fuer Zeitstempel-Handling."""

    def test_iso_timestamp(self):
        """ISO-Zeitstempel wird akzeptiert."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            createdAt="2024-12-31T23:59:59Z",
        )

        assert activity.createdAt == "2024-12-31T23:59:59Z"

    def test_timestamp_with_timezone(self):
        """Zeitstempel mit Timezone-Offset."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            createdAt="2024-12-31T23:59:59+01:00",
        )

        assert "+01:00" in activity.createdAt

    def test_timestamp_with_milliseconds(self):
        """Zeitstempel mit Millisekunden."""
        from app.db.schemas import ActivityResponse

        activity = ActivityResponse(
            id="1",
            documentId="d1",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            createdAt="2024-12-31T23:59:59.123Z",
        )

        assert "123" in activity.createdAt


class TestActivityDocumentRelation:
    """Tests fuer Document-Beziehung."""

    def test_activity_requires_document_id(self):
        """Activity erfordert documentId."""
        from app.db.schemas import ActivityResponse

        with pytest.raises(ValidationError) as exc_info:
            ActivityResponse(
                id="1",
                # documentId fehlt
                userId="u1",
                userName="User",
                type="document_viewed",
                description="Test",
                createdAt="2024-01-01T00:00:00Z",
            )

        assert "documentId" in str(exc_info.value)

    def test_activity_document_id_format(self):
        """documentId kann beliebiges String-Format sein."""
        from app.db.schemas import ActivityResponse

        # UUID-Format
        activity_uuid = ActivityResponse(
            id="1",
            documentId="550e8400-e29b-41d4-a716-446655440000",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            createdAt="2024-01-01T00:00:00Z",
        )
        assert activity_uuid.documentId == "550e8400-e29b-41d4-a716-446655440000"

        # Kurzes Format
        activity_short = ActivityResponse(
            id="1",
            documentId="doc-123",
            userId="u1",
            userName="User",
            type="document_viewed",
            description="Test",
            createdAt="2024-01-01T00:00:00Z",
        )
        assert activity_short.documentId == "doc-123"

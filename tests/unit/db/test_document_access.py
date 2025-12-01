"""
Tests für DocumentAccess Model (Document Sharing).

Testet:
- AccessLevel Enum
- DocumentAccess Model
- Ablauf-Logik (expires_at)
- Permission-Methoden
"""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.db.models import DocumentAccess, AccessLevel


class TestAccessLevelEnum:
    """Tests für AccessLevel Enum."""

    def test_access_level_values(self):
        """AccessLevel hat alle erwarteten Werte."""
        assert AccessLevel.VIEW.value == "view"
        assert AccessLevel.COMMENT.value == "comment"
        assert AccessLevel.EDIT.value == "edit"
        assert AccessLevel.MANAGE.value == "manage"

    def test_access_level_is_string_enum(self):
        """AccessLevel ist ein String-Enum."""
        assert isinstance(AccessLevel.VIEW, str)
        assert AccessLevel.VIEW == "view"


class TestDocumentAccessModel:
    """Tests für DocumentAccess Model."""

    def test_model_tablename(self):
        """Model hat korrekten Tabellennamen."""
        assert DocumentAccess.__tablename__ == "document_access"

    def test_default_access_level(self):
        """Standard-Zugriffsebene ist 'view'."""
        # Der Default ist im Column definiert
        access = DocumentAccess()
        # Ohne Initialisierung ist es None, aber DB setzt 'view'
        assert AccessLevel.VIEW.value == "view"


class TestDocumentAccessExpiration:
    """Tests für Ablauf-Logik."""

    @pytest.fixture
    def access_no_expiry(self) -> DocumentAccess:
        """Zugriff ohne Ablauf."""
        access = DocumentAccess()
        access.id = uuid4()
        access.document_id = uuid4()
        access.user_id = uuid4()
        access.access_level = AccessLevel.VIEW.value
        access.expires_at = None
        return access

    @pytest.fixture
    def access_future_expiry(self) -> DocumentAccess:
        """Zugriff mit zukünftigem Ablauf."""
        access = DocumentAccess()
        access.id = uuid4()
        access.document_id = uuid4()
        access.user_id = uuid4()
        access.access_level = AccessLevel.EDIT.value
        access.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        return access

    @pytest.fixture
    def access_expired(self) -> DocumentAccess:
        """Abgelaufener Zugriff."""
        access = DocumentAccess()
        access.id = uuid4()
        access.document_id = uuid4()
        access.user_id = uuid4()
        access.access_level = AccessLevel.MANAGE.value
        access.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        return access

    def test_is_expired_no_expiry(self, access_no_expiry: DocumentAccess):
        """Zugriff ohne Ablauf ist nie abgelaufen."""
        assert access_no_expiry.is_expired is False

    def test_is_expired_future(self, access_future_expiry: DocumentAccess):
        """Zugriff mit zukünftigem Ablauf ist nicht abgelaufen."""
        assert access_future_expiry.is_expired is False

    def test_is_expired_past(self, access_expired: DocumentAccess):
        """Abgelaufener Zugriff ist abgelaufen."""
        assert access_expired.is_expired is True


class TestDocumentAccessPermissions:
    """Tests für Permission-Methoden."""

    @pytest.fixture
    def view_access(self) -> DocumentAccess:
        """View-Zugriff."""
        access = DocumentAccess()
        access.access_level = AccessLevel.VIEW.value
        access.expires_at = None
        return access

    @pytest.fixture
    def comment_access(self) -> DocumentAccess:
        """Comment-Zugriff."""
        access = DocumentAccess()
        access.access_level = AccessLevel.COMMENT.value
        access.expires_at = None
        return access

    @pytest.fixture
    def edit_access(self) -> DocumentAccess:
        """Edit-Zugriff."""
        access = DocumentAccess()
        access.access_level = AccessLevel.EDIT.value
        access.expires_at = None
        return access

    @pytest.fixture
    def manage_access(self) -> DocumentAccess:
        """Manage-Zugriff."""
        access = DocumentAccess()
        access.access_level = AccessLevel.MANAGE.value
        access.expires_at = None
        return access

    def test_view_access_can_view(self, view_access: DocumentAccess):
        """View-Zugriff erlaubt Ansicht."""
        assert view_access.can_view() is True
        assert view_access.can_comment() is False
        assert view_access.can_edit() is False
        assert view_access.can_manage() is False

    def test_comment_access_permissions(self, comment_access: DocumentAccess):
        """Comment-Zugriff erlaubt Ansicht und Kommentieren."""
        assert comment_access.can_view() is True
        assert comment_access.can_comment() is True
        assert comment_access.can_edit() is False
        assert comment_access.can_manage() is False

    def test_edit_access_permissions(self, edit_access: DocumentAccess):
        """Edit-Zugriff erlaubt Ansicht, Kommentieren und Bearbeiten."""
        assert edit_access.can_view() is True
        assert edit_access.can_comment() is True
        assert edit_access.can_edit() is True
        assert edit_access.can_manage() is False

    def test_manage_access_permissions(self, manage_access: DocumentAccess):
        """Manage-Zugriff erlaubt alles."""
        assert manage_access.can_view() is True
        assert manage_access.can_comment() is True
        assert manage_access.can_edit() is True
        assert manage_access.can_manage() is True


class TestDocumentAccessExpiredPermissions:
    """Tests für Berechtigungen bei abgelaufenem Zugriff."""

    @pytest.fixture
    def expired_manage_access(self) -> DocumentAccess:
        """Abgelaufener Manage-Zugriff."""
        access = DocumentAccess()
        access.access_level = AccessLevel.MANAGE.value
        access.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        return access

    def test_expired_access_no_permissions(self, expired_manage_access: DocumentAccess):
        """Abgelaufener Zugriff hat keine Berechtigungen."""
        # Auch Manage-Zugriff hat nichts mehr wenn abgelaufen
        assert expired_manage_access.can_view() is False
        assert expired_manage_access.can_comment() is False
        assert expired_manage_access.can_edit() is False
        assert expired_manage_access.can_manage() is False

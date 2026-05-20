# -*- coding: utf-8 -*-
"""
Tests fuer Collaboration Service.

Feature: Echtzeit-Kollaboration (Document Locking, @Mentions, Activity Feed, Presence)
"""

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Patch app.db.base BEFORE any import that touches models_collaboration.
# models_collaboration.py does ``from app.db.base import Base`` which fails
# because app.db.base does not exist.  We inject a shim module that exposes
# the real ``Base`` from app.db.models.
# ---------------------------------------------------------------------------
import app.db.models as _models_mod  # noqa: E402

_base_shim = type(sys)("app.db.base")
_base_shim.Base = _models_mod.Base
sys.modules.setdefault("app.db.base", _base_shim)

from app.services.collaboration_service import (  # noqa: E402
    ActivityAction,
    ActivityEntry,
    CollaborationService,
    DocumentLock,
    LockType,
    Mention,
)
from app.services.realtime.event_broadcaster import RealtimeEventType  # noqa: E402


def _make_mock_broadcaster() -> MagicMock:
    """Create a mock EventBroadcaster that has RealtimeEventType as an attribute."""
    mock = MagicMock()
    mock.RealtimeEventType = RealtimeEventType
    mock._broadcast_event = AsyncMock()
    mock.emit_user_mention = AsyncMock()
    return mock


@pytest.fixture
def mock_broadcaster():
    """Mock EventBroadcaster."""
    return _make_mock_broadcaster()


@pytest.fixture
def collaboration_service(mock_broadcaster):
    """Fixture fuer CollaborationService."""
    with patch(
        "app.services.collaboration_service.get_event_broadcaster",
        return_value=mock_broadcaster,
    ):
        service = CollaborationService()
    return service


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    """Mock Redis Client."""
    redis = AsyncMock()
    redis._redis = AsyncMock()
    redis._redis.setex = AsyncMock()
    redis._redis.get = AsyncMock()
    redis._redis.delete = AsyncMock()
    return redis


@pytest.fixture
def document_id():
    """Test Document-ID."""
    return uuid.uuid4()


@pytest.fixture
def user_id():
    """Test User-ID."""
    return uuid.uuid4()


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_user():
    """Mock User Model."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.first_name = "Max"
    user.last_name = "Mustermann"
    user.email = "max.mustermann@example.com"
    return user


# ============================================================================
# Document Locking Tests
# ============================================================================


class TestDocumentLocking:
    """Tests fuer Document Locking Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
        mock_user,
    ):
        """Test: Lock erfolgreich erworben."""
        # Mock Redis
        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            # Mock check_lock (kein existierender Lock)
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=None,
            ):
                # Mock User lookup
                mock_db.get.return_value = mock_user

                # Acquire Lock
                lock = await collaboration_service.acquire_lock(
                    db=mock_db,
                    document_id=document_id,
                    user_id=user_id,
                    lock_type=LockType.EDIT,
                )

        # Assertions
        assert lock.document_id == document_id
        assert lock.locked_by == user_id
        assert lock.locked_by_name == "Max Mustermann"
        assert lock.lock_type == LockType.EDIT
        assert mock_redis._redis.setex.called

    @pytest.mark.asyncio
    async def test_acquire_lock_already_locked_by_other(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Lock fehlschlaegt wenn bereits von anderem User gesperrt."""
        other_user_id = uuid.uuid4()
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=other_user_id,
            locked_by_name="Other User",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                # Should raise ValueError
                with pytest.raises(ValueError, match="bereits von Other User gesperrt"):
                    await collaboration_service.acquire_lock(
                        db=mock_db,
                        document_id=document_id,
                        user_id=user_id,
                        lock_type=LockType.EDIT,
                    )

    @pytest.mark.asyncio
    async def test_acquire_lock_refresh_existing(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Lock wird automatisch erneuert wenn bereits vom selben User gesperrt."""
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name="Max Mustermann",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                with patch.object(
                    collaboration_service,
                    "refresh_lock",
                    return_value=existing_lock,
                ) as mock_refresh:
                    lock = await collaboration_service.acquire_lock(
                        db=mock_db,
                        document_id=document_id,
                        user_id=user_id,
                        lock_type=LockType.EDIT,
                    )

        # Should call refresh_lock
        mock_refresh.assert_called_once_with(mock_db, document_id, user_id)
        assert lock.locked_by == user_id

    @pytest.mark.asyncio
    async def test_release_lock_success(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Lock erfolgreich freigegeben."""
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name="Max Mustermann",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                result = await collaboration_service.release_lock(
                    db=mock_db,
                    document_id=document_id,
                    user_id=user_id,
                )

        assert result is True
        mock_redis._redis.delete.assert_called_once_with(f"doc_lock:{document_id}")

    @pytest.mark.asyncio
    async def test_release_lock_not_locked(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Release gibt False zurueck wenn kein Lock existiert."""
        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=None,
            ):
                result = await collaboration_service.release_lock(
                    db=mock_db,
                    document_id=document_id,
                    user_id=user_id,
                )

        assert result is False

    @pytest.mark.asyncio
    async def test_release_lock_wrong_user(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Release fehlschlaegt wenn User nicht Owner ist."""
        other_user_id = uuid.uuid4()
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=other_user_id,
            locked_by_name="Other User",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                with pytest.raises(ValueError, match="Nur der Lock-Owner"):
                    await collaboration_service.release_lock(
                        db=mock_db,
                        document_id=document_id,
                        user_id=user_id,
                    )

    @pytest.mark.asyncio
    async def test_check_lock_exists(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Check Lock gibt existierenden Lock zurueck."""
        lock_data = {
            "document_id": str(document_id),
            "locked_by": str(user_id),
            "locked_by_name": "Max Mustermann",
            "locked_at": "2025-02-13T10:00:00+00:00",
            "lock_type": "edit",
            "expires_at": "2025-02-13T10:30:00+00:00",
        }

        mock_redis._redis.get.return_value = json.dumps(lock_data)

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            lock = await collaboration_service.check_lock(
                db=mock_db,
                document_id=document_id,
            )

        assert lock is not None
        assert lock.document_id == document_id
        assert lock.locked_by == user_id
        assert lock.lock_type == LockType.EDIT

    @pytest.mark.asyncio
    async def test_check_lock_not_exists(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
    ):
        """Test: Check Lock gibt None zurueck wenn nicht gesperrt."""
        mock_redis._redis.get.return_value = None

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            lock = await collaboration_service.check_lock(
                db=mock_db,
                document_id=document_id,
            )

        assert lock is None

    @pytest.mark.asyncio
    async def test_force_release_success(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Force Release entfernt Lock erfolgreich."""
        admin_id = uuid.uuid4()
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name="Max Mustermann",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                result = await collaboration_service.force_release(
                    db=mock_db,
                    document_id=document_id,
                    admin_user_id=admin_id,
                )

        assert result is True
        mock_redis._redis.delete.assert_called_once_with(f"doc_lock:{document_id}")

    @pytest.mark.asyncio
    async def test_force_release_not_locked(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
    ):
        """Test: Force Release gibt False zurueck wenn kein Lock existiert."""
        admin_id = uuid.uuid4()

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=None,
            ):
                result = await collaboration_service.force_release(
                    db=mock_db,
                    document_id=document_id,
                    admin_user_id=admin_id,
                )

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_lock_success(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Lock wird erfolgreich erneuert."""
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name="Max Mustermann",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                lock = await collaboration_service.refresh_lock(
                    db=mock_db,
                    document_id=document_id,
                    user_id=user_id,
                )

        assert lock.document_id == document_id
        assert lock.locked_by == user_id
        assert mock_redis._redis.setex.called

    @pytest.mark.asyncio
    async def test_refresh_lock_not_exists(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Refresh fehlschlaegt wenn kein Lock existiert."""
        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="Keine Sperre vorhanden"):
                    await collaboration_service.refresh_lock(
                        db=mock_db,
                        document_id=document_id,
                        user_id=user_id,
                    )

    @pytest.mark.asyncio
    async def test_refresh_lock_wrong_user(
        self,
        collaboration_service,
        mock_db,
        mock_redis,
        document_id,
        user_id,
    ):
        """Test: Refresh fehlschlaegt wenn User nicht Owner ist."""
        other_user_id = uuid.uuid4()
        existing_lock = DocumentLock(
            document_id=document_id,
            locked_by=other_user_id,
            locked_by_name="Other User",
            locked_at=datetime.now(timezone.utc),
            lock_type=LockType.EDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        with patch("app.services.collaboration_service.get_redis", return_value=mock_redis):
            with patch.object(
                collaboration_service,
                "check_lock",
                return_value=existing_lock,
            ):
                with pytest.raises(ValueError, match="Nur der Lock-Owner"):
                    await collaboration_service.refresh_lock(
                        db=mock_db,
                        document_id=document_id,
                        user_id=user_id,
                    )


# ============================================================================
# Activity Feed Tests
# ============================================================================


class TestActivityFeed:
    """Tests fuer Activity Feed Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_record_activity_success(
        self,
        collaboration_service,
        mock_db,
        user_id,
        document_id,
        mock_user,
    ):
        """Test: Activity wird erfolgreich aufgezeichnet."""
        mock_db.get.return_value = mock_user

        # Simulate refresh updating the object
        def refresh_side_effect(obj):
            pass

        mock_db.refresh.side_effect = refresh_side_effect

        # Patch DocumentActivity to avoid SQLAlchemy mapper conflict
        # (SignatureRequest is defined in two modules)
        _FakeActivity = type("DocumentActivity", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
        with patch("app.db.models_collaboration.DocumentActivity", _FakeActivity):
            entry = await collaboration_service.record_activity(
                db=mock_db,
                user_id=user_id,
                action=ActivityAction.VIEWED,
                details="Dokument angesehen",
                document_id=document_id,
            )

        assert entry.user_id == user_id
        assert entry.action == ActivityAction.VIEWED
        assert entry.details == "Dokument angesehen"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_activity_user_not_found(
        self,
        collaboration_service,
        mock_db,
        user_id,
    ):
        """Test: ValueError wenn User nicht gefunden."""
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="Benutzer nicht gefunden"):
            await collaboration_service.record_activity(
                db=mock_db,
                user_id=user_id,
                action=ActivityAction.VIEWED,
                details="Test",
            )

    @pytest.mark.asyncio
    async def test_get_document_activity(
        self,
        collaboration_service,
        mock_db,
        document_id,
        user_id,
        mock_user,
    ):
        """Test: Activity Feed fuer Dokument wird abgerufen."""
        # Mock Activities (no spec needed - just plain MagicMock)
        mock_activity = MagicMock()
        mock_activity.id = uuid.uuid4()
        mock_activity.document_id = document_id
        mock_activity.user_id = user_id
        mock_activity.action = "viewed"
        mock_activity.details = "Dokument angesehen"
        mock_activity.created_at = datetime.now(timezone.utc)

        # Mock execute result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_activity]

        # Mock User lookup
        mock_user_result = MagicMock()
        mock_user_result.scalars.return_value.all.return_value = [mock_user]
        mock_db.execute.side_effect = [mock_result, mock_user_result]

        entries = await collaboration_service.get_document_activity(
            db=mock_db,
            document_id=document_id,
            limit=50,
        )

        assert len(entries) == 1
        assert entries[0].user_id == user_id
        assert entries[0].action == ActivityAction.VIEWED

    @pytest.mark.asyncio
    async def test_get_user_activity_feed(
        self,
        collaboration_service,
        mock_db,
        user_id,
        company_id,
        mock_user,
    ):
        """Test: User Activity Feed wird abgerufen."""
        mock_activity = MagicMock()
        mock_activity.id = uuid.uuid4()
        mock_activity.document_id = uuid.uuid4()
        mock_activity.user_id = user_id
        mock_activity.action = "edited"
        mock_activity.details = "Dokument bearbeitet"
        mock_activity.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_activity]
        mock_db.execute.return_value = mock_result
        mock_db.get.return_value = mock_user

        entries = await collaboration_service.get_user_activity_feed(
            db=mock_db,
            user_id=user_id,
            company_id=company_id,
            limit=50,
        )

        assert len(entries) == 1
        assert entries[0].user_id == user_id
        assert entries[0].action == ActivityAction.EDITED

    @pytest.mark.asyncio
    async def test_get_company_activity_feed(
        self,
        collaboration_service,
        mock_db,
        company_id,
        user_id,
        mock_user,
    ):
        """Test: Company Activity Feed wird abgerufen."""
        mock_activity = MagicMock()
        mock_activity.id = uuid.uuid4()
        mock_activity.document_id = uuid.uuid4()
        mock_activity.user_id = user_id
        mock_activity.action = "uploaded"
        mock_activity.details = "Dokument hochgeladen"
        mock_activity.created_at = datetime.now(timezone.utc)

        # Mock execute results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_activity]

        mock_user_result = MagicMock()
        mock_user_result.scalars.return_value.all.return_value = [mock_user]

        mock_db.execute.side_effect = [mock_result, mock_user_result]

        entries = await collaboration_service.get_company_activity_feed(
            db=mock_db,
            company_id=company_id,
            limit=50,
            since=None,
        )

        assert len(entries) == 1
        assert entries[0].action == ActivityAction.UPLOADED

    @pytest.mark.asyncio
    async def test_get_company_activity_feed_with_since(
        self,
        collaboration_service,
        mock_db,
        company_id,
    ):
        """Test: Company Activity Feed mit since-Filter."""
        since_date = datetime.now(timezone.utc) - timedelta(days=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        entries = await collaboration_service.get_company_activity_feed(
            db=mock_db,
            company_id=company_id,
            limit=50,
            since=since_date,
        )

        assert isinstance(entries, list)


# ============================================================================
# @Mentions Tests
# ============================================================================


class TestMentions:
    """Tests fuer @Mentions Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_create_mention_success(
        self,
        collaboration_service,
        mock_db,
        document_id,
        user_id,
    ):
        """Test: Mention wird erfolgreich erstellt."""
        mentioned_user_id = uuid.uuid4()
        mentioned_by_id = user_id

        mock_mention_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        def refresh_side_effect(obj):
            # Copy mock data to obj
            obj.id = mock_mention_id
            obj.document_id = document_id
            obj.mentioned_user_id = mentioned_user_id
            obj.mentioned_by_id = mentioned_by_id
            obj.context = "Bitte pruefen @max"
            obj.read = False
            obj.created_at = now

        mock_db.refresh.side_effect = refresh_side_effect

        # Patch DocumentMention to avoid SQLAlchemy mapper conflict
        _FakeMention = type("DocumentMention", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
        with patch("app.db.models_collaboration.DocumentMention", _FakeMention):
            mention = await collaboration_service.create_mention(
                db=mock_db,
                document_id=document_id,
                mentioned_user_id=mentioned_user_id,
                mentioned_by_id=mentioned_by_id,
                context="Bitte pruefen @max",
            )

        assert mention.document_id == document_id
        assert mention.mentioned_user_id == mentioned_user_id
        assert mention.read is False
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_mention_truncates_context(
        self,
        collaboration_service,
        mock_db,
        document_id,
        user_id,
    ):
        """Test: Langer Kontext wird auf 500 Zeichen gekuerzt."""
        mentioned_user_id = uuid.uuid4()
        long_context = "A" * 600

        mock_mention_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        def refresh_side_effect(obj):
            obj.id = mock_mention_id
            obj.document_id = document_id
            obj.mentioned_user_id = mentioned_user_id
            obj.mentioned_by_id = user_id
            obj.context = "A" * 500
            obj.read = False
            obj.created_at = now

        mock_db.refresh.side_effect = refresh_side_effect

        # Patch DocumentMention to avoid SQLAlchemy mapper conflict
        _FakeMention = type("DocumentMention", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
        with patch("app.db.models_collaboration.DocumentMention", _FakeMention):
            mention = await collaboration_service.create_mention(
                db=mock_db,
                document_id=document_id,
                mentioned_user_id=mentioned_user_id,
                mentioned_by_id=user_id,
                context=long_context,
            )

        assert len(mention.context) == 500

    @pytest.mark.asyncio
    async def test_get_unread_mentions(
        self,
        collaboration_service,
        mock_db,
        user_id,
        company_id,
        document_id,
    ):
        """Test: Ungelesene Mentions werden abgerufen."""
        mock_mention = MagicMock()
        mock_mention.id = uuid.uuid4()
        mock_mention.document_id = document_id
        mock_mention.mentioned_user_id = user_id
        mock_mention.mentioned_by_id = uuid.uuid4()
        mock_mention.context = "Bitte pruefen"
        mock_mention.read = False
        mock_mention.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_mention]
        mock_db.execute.return_value = mock_result

        mentions = await collaboration_service.get_unread_mentions(
            db=mock_db,
            user_id=user_id,
            company_id=company_id,
        )

        assert len(mentions) == 1
        assert mentions[0].mentioned_user_id == user_id
        assert mentions[0].read is False

    @pytest.mark.asyncio
    async def test_mark_mention_read_success(
        self,
        collaboration_service,
        mock_db,
        user_id,
    ):
        """Test: Mention wird als gelesen markiert."""
        mention_id = uuid.uuid4()

        mock_mention = MagicMock()
        mock_mention.id = mention_id
        mock_mention.mentioned_user_id = user_id
        mock_mention.read = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_mention
        mock_db.execute.return_value = mock_result

        result = await collaboration_service.mark_mention_read(
            db=mock_db,
            mention_id=mention_id,
            user_id=user_id,
        )

        assert result is True
        assert mock_mention.read is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_mention_read_not_found(
        self,
        collaboration_service,
        mock_db,
        user_id,
    ):
        """Test: Mark read gibt False zurueck wenn Mention nicht gefunden."""
        mention_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await collaboration_service.mark_mention_read(
            db=mock_db,
            mention_id=mention_id,
            user_id=user_id,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_mention_read_wrong_user(
        self,
        collaboration_service,
        mock_db,
        user_id,
    ):
        """Test: Mark read schlaegt fehl wenn User nicht Owner ist."""
        mention_id = uuid.uuid4()

        # Mention gehoert anderem User
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await collaboration_service.mark_mention_read(
            db=mock_db,
            mention_id=mention_id,
            user_id=user_id,
        )

        assert result is False

    def test_parse_mentions(self, collaboration_service):
        """Test: @Mentions werden aus Text extrahiert."""
        text = "Hey @max.mustermann bitte @anna.schmidt kontaktieren"

        mentions = collaboration_service.parse_mentions(text)

        assert len(mentions) == 2
        assert "max.mustermann" in mentions
        assert "anna.schmidt" in mentions

    def test_parse_mentions_no_matches(self, collaboration_service):
        """Test: Kein @ im Text -> leere Liste."""
        text = "Keine Mentions hier"

        mentions = collaboration_service.parse_mentions(text)

        assert len(mentions) == 0


# ============================================================================
# Presence Tests
# ============================================================================


class TestPresence:
    """Tests fuer Presence Tracking."""

    @pytest.mark.asyncio
    async def test_get_document_viewers(
        self,
        collaboration_service,
        document_id,
    ):
        """Test: Viewers werden ueber WebSocket Manager abgerufen."""
        mock_viewers = [
            {"user_id": str(uuid.uuid4()), "user_name": "Max Mustermann"},
            {"user_id": str(uuid.uuid4()), "user_name": "Anna Schmidt"},
        ]

        with patch(
            "app.services.realtime.realtime_websocket_manager.get_realtime_ws_manager"
        ) as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_document_viewers = AsyncMock(return_value=mock_viewers)
            mock_get_manager.return_value = mock_manager

            viewers = await collaboration_service.get_document_viewers(
                document_id=document_id
            )

        assert len(viewers) == 2
        assert viewers[0]["user_name"] == "Max Mustermann"
        assert viewers[1]["user_name"] == "Anna Schmidt"


# ============================================================================
# Data Model Tests
# ============================================================================


class TestDataModels:
    """Tests fuer Datenmodelle."""

    def test_document_lock_to_dict(self):
        """Test: DocumentLock.to_dict() Serialisierung."""
        document_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        lock = DocumentLock(
            document_id=document_id,
            locked_by=user_id,
            locked_by_name="Max Mustermann",
            locked_at=now,
            lock_type=LockType.EDIT,
            expires_at=now + timedelta(minutes=30),
        )

        data = lock.to_dict()

        assert data["document_id"] == str(document_id)
        assert data["locked_by"] == str(user_id)
        assert data["locked_by_name"] == "Max Mustermann"
        assert data["lock_type"] == "edit"

    def test_mention_to_dict(self):
        """Test: Mention.to_dict() Serialisierung."""
        mention_id = uuid.uuid4()
        document_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mention = Mention(
            id=mention_id,
            document_id=document_id,
            mentioned_user_id=user_id,
            mentioned_by_id=uuid.uuid4(),
            context="Bitte pruefen",
            read=False,
            created_at=now,
        )

        data = mention.to_dict()

        assert data["id"] == str(mention_id)
        assert data["document_id"] == str(document_id)
        assert data["mentioned_user_id"] == str(user_id)
        assert data["read"] is False

    def test_activity_entry_to_dict(self):
        """Test: ActivityEntry.to_dict() Serialisierung."""
        activity_id = uuid.uuid4()
        document_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        entry = ActivityEntry(
            id=activity_id,
            document_id=document_id,
            user_id=user_id,
            user_name="Max Mustermann",
            action=ActivityAction.VIEWED,
            details="Dokument angesehen",
            created_at=now,
        )

        data = entry.to_dict()

        assert data["id"] == str(activity_id)
        assert data["document_id"] == str(document_id)
        assert data["user_id"] == str(user_id)
        assert data["action"] == "viewed"
        assert data["details"] == "Dokument angesehen"

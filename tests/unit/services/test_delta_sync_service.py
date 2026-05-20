# -*- coding: utf-8 -*-
"""Unit tests for Delta Sync Service (Offline-First Synchronization)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.sync.delta_sync_service import (
    DeltaSyncService,
    DeltaResponse,
    ChangeRecord,
    SyncResult,
    ConflictResolution,
)


# ============================================================================
# Pull Delta Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pull_delta_changes():
    """Test DeltaSyncService returns changes since timestamp."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_db = AsyncMock()

    # Mock 3 geänderte Dokumente
    mock_docs = []
    for i in range(3):
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.filename = f"doc_{i}.pdf"
        mock_doc.status = "completed"
        mock_doc.company_id = company_id
        mock_doc.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30-i)
        mock_doc.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_docs.append(mock_doc)

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_docs
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    delta = await service.get_changes_since(
        entity_type="document",
        since=since,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert isinstance(delta, DeltaResponse)
    assert delta.entity_type == "document"
    assert len(delta.changes) == 3
    assert delta.has_more is False
    assert all("id" in change for change in delta.changes)


@pytest.mark.asyncio
async def test_pull_delta_no_changes():
    """Test DeltaSyncService returns empty when no changes."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_db = AsyncMock()

    # Mock keine Änderungen
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    delta = await service.get_changes_since(
        entity_type="document",
        since=since,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(delta.changes) == 0
    assert delta.has_more is False


# ============================================================================
# Push Sync Tests
# ============================================================================


@pytest.mark.asyncio
async def test_push_sync_new_record():
    """Test DeltaSyncService creates new record."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    user_id = uuid4()

    new_id = uuid4()
    change = ChangeRecord(
        entity_type="document",
        entity_id=new_id,
        operation="create",
        data={"filename": "new.pdf", "status": "pending"},
        client_timestamp=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()

    # Mock: Entity existiert noch nicht
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()

    # Act
    sync_result = await service.push_changes(
        changes=[change],
        company_id=company_id,
        user_id=user_id,
        db=mock_db,
    )

    # Assert
    assert isinstance(sync_result, SyncResult)
    assert sync_result.accepted == 1
    assert sync_result.rejected == 0
    assert len(sync_result.conflicts) == 0
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_push_sync_update_record():
    """Test DeltaSyncService updates existing record."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    user_id = uuid4()

    doc_id = uuid4()
    change = ChangeRecord(
        entity_type="document",
        entity_id=doc_id,
        operation="update",
        data={"status": "completed", "ocr_text": "Test"},
        client_timestamp=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()

    # Mock: Existierendes Dokument
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "processing"
    mock_doc.ocr_text = None
    mock_doc.company_id = company_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    sync_result = await service.push_changes(
        changes=[change],
        company_id=company_id,
        user_id=user_id,
        db=mock_db,
    )

    # Assert
    assert sync_result.accepted == 1
    assert sync_result.rejected == 0
    assert mock_doc.status == "completed"
    assert mock_doc.ocr_text == "Test"


@pytest.mark.asyncio
async def test_push_sync_conflict_last_write_wins():
    """Test DeltaSyncService conflict resolution - last write wins."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    user_id = uuid4()

    doc_id = uuid4()

    # Client change (neuerer Timestamp)
    client_ts = datetime.now(timezone.utc)
    change = ChangeRecord(
        entity_type="document",
        entity_id=doc_id,
        operation="update",
        data={"status": "completed", "updated_at": client_ts.isoformat()},
        client_timestamp=client_ts,
        version=1,  # Erwartet Version 1
    )

    mock_db = AsyncMock()

    # Mock: Server hat Version 2 (Konflikt!)
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "failed"
    mock_doc.version = 2  # Höhere Version
    mock_doc.updated_at = client_ts - timedelta(minutes=5)  # Älterer Timestamp
    mock_doc.company_id = company_id

    # Mock _item_to_change
    def mock_item_to_change(item):
        return {
            "id": str(item.id),
            "status": item.status,
            "updated_at": item.updated_at.isoformat() if hasattr(item.updated_at, 'isoformat') else str(item.updated_at),
            "version": item.version,
        }

    service._item_to_change = mock_item_to_change

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    sync_result = await service.push_changes(
        changes=[change],
        company_id=company_id,
        user_id=user_id,
        conflict_resolution=ConflictResolution.LAST_WRITE_WINS,
        db=mock_db,
    )

    # Assert
    assert sync_result.rejected == 1  # Version mismatch
    assert len(sync_result.conflicts) == 1
    assert sync_result.conflicts[0]["reason"] == "version_mismatch"
    # Last write wins: Client hat neueren Timestamp -> Client gewinnt
    assert mock_doc.status == "completed"


@pytest.mark.asyncio
async def test_push_sync_conflict_server_wins():
    """Test DeltaSyncService conflict resolution - server wins."""
    # Arrange
    service = DeltaSyncService()

    doc_id = uuid4()
    server_version = {
        "id": str(doc_id),
        "status": "server_state",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client_version = {
        "id": str(doc_id),
        "status": "client_state",
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }

    # Act
    resolved = await service.resolve_conflict(
        entity_type="document",
        entity_id=doc_id,
        server_version=server_version,
        client_version=client_version,
        strategy=ConflictResolution.SERVER_WINS,
    )

    # Assert
    assert resolved["status"] == "server_state"


@pytest.mark.asyncio
async def test_push_sync_conflict_client_wins():
    """Test DeltaSyncService conflict resolution - client wins."""
    # Arrange
    service = DeltaSyncService()

    doc_id = uuid4()
    server_version = {
        "id": str(doc_id),
        "status": "server_state",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client_version = {
        "id": str(doc_id),
        "status": "client_state",
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }

    # Act
    resolved = await service.resolve_conflict(
        entity_type="document",
        entity_id=doc_id,
        server_version=server_version,
        client_version=client_version,
        strategy=ConflictResolution.CLIENT_WINS,
    )

    # Assert
    assert resolved["status"] == "client_state"


@pytest.mark.asyncio
async def test_push_sync_conflict_merge():
    """Test DeltaSyncService conflict resolution - merge strategy."""
    # Arrange
    service = DeltaSyncService()

    doc_id = uuid4()
    server_version = {
        "id": str(doc_id),
        "status": "completed",
        "ocr_text": "Server text",
        "tags": ["server_tag"],
        "metadata": {"key1": "server_value"},
    }
    client_version = {
        "id": str(doc_id),
        "status": "completed",
        "ocr_confidence": 0.95,
        "tags": ["client_tag"],
        "metadata": {"key2": "client_value"},
    }

    # Act
    resolved = await service.resolve_conflict(
        entity_type="document",
        entity_id=doc_id,
        server_version=server_version,
        client_version=client_version,
        strategy=ConflictResolution.MERGE,
    )

    # Assert
    assert resolved["status"] == "completed"
    assert resolved["ocr_text"] == "Server text"  # Server hatte Wert
    assert resolved["ocr_confidence"] == 0.95  # Client hatte Wert (Server None)
    # Tags sollten gemergt sein (unique)
    assert "server_tag" in resolved["tags"]
    assert "client_tag" in resolved["tags"]
    # Metadata sollte gemergt sein
    assert resolved["metadata"]["key1"] == "server_value"
    assert resolved["metadata"]["key2"] == "client_value"


@pytest.mark.asyncio
async def test_optimistic_locking():
    """Test DeltaSyncService detects version mismatch (optimistic locking)."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    user_id = uuid4()

    doc_id = uuid4()
    change = ChangeRecord(
        entity_type="document",
        entity_id=doc_id,
        operation="update",
        data={"status": "completed"},
        client_timestamp=datetime.now(timezone.utc),
        version=1,  # Client erwartet Version 1
    )

    mock_db = AsyncMock()

    # Mock: Server hat Version 5 (viel neuere Version)
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "processing"
    mock_doc.version = 5  # Server version
    mock_doc.company_id = company_id
    mock_doc.updated_at = datetime.now(timezone.utc)

    def mock_item_to_change(item):
        return {
            "id": str(item.id),
            "status": item.status,
            "version": item.version,
            "updated_at": item.updated_at.isoformat(),
        }

    service._item_to_change = mock_item_to_change

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    sync_result = await service.push_changes(
        changes=[change],
        company_id=company_id,
        user_id=user_id,
        db=mock_db,
    )

    # Assert
    assert sync_result.rejected == 1
    assert len(sync_result.conflicts) == 1
    assert sync_result.conflicts[0]["reason"] == "version_mismatch"


@pytest.mark.asyncio
async def test_sync_multi_tenant():
    """Test DeltaSyncService preserves company isolation."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    user_id = uuid4()

    new_id = uuid4()
    change = ChangeRecord(
        entity_type="document",
        entity_id=new_id,
        operation="create",
        data={"filename": "test.pdf"},
        client_timestamp=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    created_item = None
    def mock_add(item):
        nonlocal created_item
        created_item = item

    mock_db.add = mock_add

    # Act
    await service.push_changes(
        changes=[change],
        company_id=company_id,
        user_id=user_id,
        db=mock_db,
    )

    # Assert
    assert created_item is not None
    assert created_item.company_id == company_id


@pytest.mark.asyncio
async def test_delta_has_more_pagination():
    """Test DeltaSyncService indicates has_more for pagination."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_db = AsyncMock()

    # Mock mehr als limit Items (101 wenn limit=100)
    mock_docs = []
    for i in range(101):  # BATCH_SIZE + 1
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.filename = f"doc_{i}.pdf"
        mock_doc.updated_at = datetime.now(timezone.utc)
        mock_docs.append(mock_doc)

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_docs
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    delta = await service.get_changes_since(
        entity_type="document",
        since=since,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert delta.has_more is True
    assert len(delta.changes) == 100  # Sollte auf BATCH_SIZE gekürzt sein


@pytest.mark.asyncio
async def test_invalid_entity_type():
    """Test DeltaSyncService rejects invalid entity types."""
    # Arrange
    service = DeltaSyncService()
    company_id = uuid4()
    since = datetime.now(timezone.utc)
    mock_db = AsyncMock()

    # Act & Assert
    with pytest.raises(ValueError, match="Ungültiger Entity-Typ"):
        await service.get_changes_since(
            entity_type="malicious_type",
            since=since,
            company_id=company_id,
            db=mock_db,
        )

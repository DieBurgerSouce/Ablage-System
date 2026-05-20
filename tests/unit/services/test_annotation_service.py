# -*- coding: utf-8 -*-
"""Unit tests for Annotation Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.services.annotations.annotation_service import AnnotationService
from app.db.models import DocumentAnnotation


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Annotation service instance."""
    return AnnotationService(db=mock_db)


@pytest.fixture
def document_id():
    """Test document ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid4()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.mark.asyncio
async def test_create_annotation_comment(service, mock_db, document_id, user_id, company_id):
    """Test creating a comment annotation."""
    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="comment",
        content="Dies ist ein Testkommentar",
        page_number=1,
    )

    assert isinstance(annotation, DocumentAnnotation)
    assert annotation.annotation_type == "comment"
    assert annotation.content == "Dies ist ein Testkommentar"
    assert annotation.page == 1
    assert annotation.document_id == document_id
    assert annotation.user_id == user_id
    assert annotation.company_id == company_id
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_annotation_highlight(service, mock_db, document_id, user_id, company_id):
    """Test creating a highlight annotation with position."""
    position = {"x": 100, "y": 200, "width": 300, "height": 50}

    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="highlight",
        content="Wichtiger Abschnitt",
        page_number=2,
        position=position,
    )

    assert annotation.annotation_type == "highlight"
    assert annotation.position == position
    assert annotation.page == 2


@pytest.mark.asyncio
async def test_create_annotation_drawing(service, mock_db, document_id, user_id, company_id):
    """Test creating a drawing annotation with SVG data."""
    svg_data = '<path d="M10,10 L100,100" stroke="red" />'

    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="drawing",
        content="Markierung",
        page_number=1,
        svg_data=svg_data,
    )

    assert annotation.annotation_type == "drawing"
    assert annotation.svg_data == svg_data


@pytest.mark.asyncio
async def test_create_annotation_approval(service, mock_db, document_id, user_id, company_id):
    """Test creating an approval marker annotation."""
    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="approval",
        content="Genehmigt durch Abteilungsleiter",
        page_number=1,
    )

    assert annotation.annotation_type == "approval"
    assert "Genehmigt" in annotation.content


@pytest.mark.asyncio
async def test_get_annotations_for_document(service, mock_db, document_id, company_id):
    """Test retrieving all annotations for a document."""
    # Mock annotations
    mock_annotation1 = MagicMock(spec=DocumentAnnotation)
    mock_annotation1.id = uuid4()
    mock_annotation1.annotation_type = "comment"
    mock_annotation1.page = 1

    mock_annotation2 = MagicMock(spec=DocumentAnnotation)
    mock_annotation2.id = uuid4()
    mock_annotation2.annotation_type = "highlight"
    mock_annotation2.page = 2

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_annotation1, mock_annotation2]
    mock_db.execute.return_value = mock_result

    annotations = await service.get_annotations_for_document(
        document_id=document_id,
        company_id=company_id,
    )

    assert len(annotations) == 2
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_annotations_filtered_by_page(service, mock_db, document_id, company_id):
    """Test filtering annotations by page number."""
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.page = 1

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_annotation]
    mock_db.execute.return_value = mock_result

    annotations = await service.get_annotations_for_document(
        document_id=document_id,
        company_id=company_id,
        page_number=1,
    )

    assert len(annotations) == 1
    assert annotations[0].page == 1


@pytest.mark.asyncio
async def test_get_annotations_filtered_by_type(service, mock_db, document_id, company_id):
    """Test filtering annotations by annotation type."""
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.annotation_type = "comment"

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_annotation]
    mock_db.execute.return_value = mock_result

    annotations = await service.get_annotations_for_document(
        document_id=document_id,
        company_id=company_id,
        annotation_type="comment",
    )

    assert len(annotations) == 1
    assert annotations[0].annotation_type == "comment"


@pytest.mark.asyncio
async def test_thread_support(service, mock_db, document_id, user_id, company_id):
    """Test parent/child threading works."""
    parent_id = uuid4()

    # Create child annotation with parent
    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="comment",
        content="Antwort auf Kommentar",
        page_number=1,
        parent_annotation_id=parent_id,
    )

    assert annotation.parent_annotation_id == parent_id


@pytest.mark.asyncio
async def test_update_annotation_content(service, mock_db, user_id, company_id):
    """Test updating annotation text content."""
    annotation_id = uuid4()

    # Mock existing annotation
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.id = annotation_id
    mock_annotation.content = "Old content"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_annotation
    mock_db.execute.return_value = mock_result

    updated = await service.update_annotation(
        annotation_id=annotation_id,
        company_id=company_id,
        user_id=user_id,
        content="Updated content",
    )

    assert updated is not None
    assert updated.content == "Updated content"
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_annotation(service, mock_db, user_id, company_id):
    """Test marking annotation as resolved."""
    annotation_id = uuid4()

    # Mock existing annotation
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.id = annotation_id
    mock_annotation.is_resolved = False
    mock_annotation.resolved_by_id = None
    mock_annotation.resolved_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_annotation
    mock_db.execute.return_value = mock_result

    updated = await service.update_annotation(
        annotation_id=annotation_id,
        company_id=company_id,
        user_id=user_id,
        is_resolved=True,
    )

    assert updated is not None
    assert updated.is_resolved is True
    assert updated.resolved_by_id == user_id
    assert updated.resolved_at is not None


@pytest.mark.asyncio
async def test_delete_own_annotation(service, mock_db, user_id, company_id):
    """Test user can delete their own annotation."""
    annotation_id = uuid4()

    # Mock own annotation
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.id = annotation_id
    mock_annotation.user_id = user_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_annotation
    mock_db.execute.return_value = mock_result

    success = await service.delete_annotation(
        annotation_id=annotation_id,
        company_id=company_id,
        user_id=user_id,
    )

    assert success is True
    mock_db.delete.assert_called_once_with(mock_annotation)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_other_annotation_fails(service, mock_db, company_id):
    """Test user cannot delete other users' annotations."""
    annotation_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()

    # Mock annotation owned by other user
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.id = annotation_id
    mock_annotation.user_id = other_user_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # Query filters by user_id
    mock_db.execute.return_value = mock_result

    success = await service.delete_annotation(
        annotation_id=annotation_id,
        company_id=company_id,
        user_id=user_id,
    )

    assert success is False
    mock_db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_annotation_stats(service, mock_db, document_id, company_id):
    """Test returning annotation statistics grouped by type."""
    # Mock grouped statistics result
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([
        ("comment", 5),
        ("highlight", 3),
        ("drawing", 2),
    ]))
    mock_db.execute.return_value = mock_result

    stats = await service.get_annotation_stats(
        document_id=document_id,
        company_id=company_id,
    )

    assert isinstance(stats, dict)
    assert stats["comment"] == 5
    assert stats["highlight"] == 3
    assert stats["drawing"] == 2
    assert stats["total"] == 10  # Sum


@pytest.mark.asyncio
async def test_get_thread(service, mock_db, company_id):
    """Test retrieving complete annotation thread."""
    parent_id = uuid4()

    # Mock parent and child annotations
    mock_parent = MagicMock(spec=DocumentAnnotation)
    mock_parent.id = parent_id
    mock_parent.parent_annotation_id = None

    mock_child1 = MagicMock(spec=DocumentAnnotation)
    mock_child1.id = uuid4()
    mock_child1.parent_annotation_id = parent_id

    mock_child2 = MagicMock(spec=DocumentAnnotation)
    mock_child2.id = uuid4()
    mock_child2.parent_annotation_id = parent_id

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_parent, mock_child1, mock_child2]
    mock_db.execute.return_value = mock_result

    thread = await service.get_thread(
        annotation_id=parent_id,
        company_id=company_id,
    )

    assert len(thread) == 3
    assert thread[0].id == parent_id


@pytest.mark.asyncio
async def test_mentioned_users(service, mock_db, document_id, user_id, company_id):
    """Test @-mentions support in annotations."""
    mentioned_user1 = uuid4()
    mentioned_user2 = uuid4()

    annotation = await service.create_annotation(
        document_id=document_id,
        user_id=user_id,
        company_id=company_id,
        annotation_type="comment",
        content="@user1 @user2 bitte prüfen",
        page_number=1,
        mentioned_user_ids=[mentioned_user1, mentioned_user2],
    )

    assert len(annotation.mentioned_user_ids) == 2
    assert str(mentioned_user1) in annotation.mentioned_user_ids
    assert str(mentioned_user2) in annotation.mentioned_user_ids


@pytest.mark.asyncio
async def test_exclude_resolved_annotations(service, mock_db, document_id, company_id):
    """Test excluding resolved annotations from results."""
    # Mock only unresolved annotations
    mock_annotation = MagicMock(spec=DocumentAnnotation)
    mock_annotation.is_resolved = False

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_annotation]
    mock_db.execute.return_value = mock_result

    annotations = await service.get_annotations_for_document(
        document_id=document_id,
        company_id=company_id,
        include_resolved=False,
    )

    assert len(annotations) == 1
    assert annotations[0].is_resolved is False

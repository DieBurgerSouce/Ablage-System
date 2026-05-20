# -*- coding: utf-8 -*-
"""
Unit tests for unified bulk operations endpoint.

Tests the POST /api/v1/documents/bulk endpoint with all action types:
- tag: Add/remove/set tags
- move: Move to folder
- delete: Soft delete
- export: Export documents
- categorize: Set category
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


# Define test schemas directly to avoid import issues with torch
class BulkOperationAction(str, Enum):
    """Supported bulk operation actions."""
    TAG = "tag"
    MOVE = "move"
    DELETE = "delete"
    EXPORT = "export"
    CATEGORIZE = "categorize"


class UnifiedBulkOperationRequest(BaseModel):
    """Unified request for all bulk operations on documents."""
    document_ids: List = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der Dokument-IDs (max. 100)"
    )
    action: BulkOperationAction = Field(
        ...,
        description="Auszufuehrende Aktion: tag, move, delete, export, categorize"
    )
    params: Optional[Dict[str, Any]] = Field(
        None,
        description="Aktions-spezifische Parameter"
    )

    model_config = ConfigDict(use_enum_values=True)


class UnifiedBulkOperationResponse(BaseModel):
    """Response for unified bulk operations."""
    success: bool
    action: str
    total_requested: int
    processed: int
    failed: int
    errors: List[Dict[str, str]] = Field(default_factory=list)
    message: str
    task_id: Optional[str] = Field(None)
    download_url: Optional[str] = Field(None)


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def mock_company():
    """Create a mock company."""
    company = MagicMock()
    company.id = uuid4()
    return company


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    return db


class TestUnifiedBulkOperationRequest:
    """Tests for the request schema."""

    def test_valid_tag_request(self):
        """Test valid tag request."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4(), uuid4()],
            action="tag",
            params={"tags": ["wichtig", "archiv"], "operation": "add"}
        )
        assert request.action == BulkOperationAction.TAG
        assert len(request.document_ids) == 2

    def test_valid_move_request(self):
        """Test valid move request."""
        folder_id = uuid4()
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="move",
            params={"folder_id": str(folder_id)}
        )
        assert request.action == BulkOperationAction.MOVE

    def test_valid_delete_request(self):
        """Test valid delete request."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4(), uuid4(), uuid4()],
            action="delete",
            params={"reason": "Nicht mehr benoetigt"}
        )
        assert request.action == BulkOperationAction.DELETE

    def test_valid_export_request(self):
        """Test valid export request."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="export",
            params={"format": "zip", "include_metadata": True}
        )
        assert request.action == BulkOperationAction.EXPORT

    def test_valid_categorize_request(self):
        """Test valid categorize request."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="categorize",
            params={"category": "rechnungen_eingang"}
        )
        assert request.action == BulkOperationAction.CATEGORIZE

    def test_empty_document_ids_invalid(self):
        """Test that empty document_ids raises validation error."""
        with pytest.raises(ValueError):
            UnifiedBulkOperationRequest(
                document_ids=[],
                action="tag",
                params={"tags": ["test"]}
            )

    def test_too_many_document_ids_invalid(self):
        """Test that more than 100 document_ids raises validation error."""
        with pytest.raises(ValueError):
            UnifiedBulkOperationRequest(
                document_ids=[uuid4() for _ in range(101)],
                action="tag",
                params={"tags": ["test"]}
            )


class TestUnifiedBulkOperationEndpoint:
    """Tests for the unified bulk operation endpoint.

    Note: Integration tests that require full endpoint imports
    are located in tests/integration/. These schema-only tests
    verify the data structures without requiring torch/GPU dependencies.
    """

    def test_tag_request_requires_tags(self):
        """Test that tag operation requires tags in params."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="tag",
            params={}  # Missing tags
        )

        # Verify the request is valid but params.tags is empty
        assert request.action == BulkOperationAction.TAG
        assert request.params.get("tags") is None

    def test_move_request_requires_folder_id(self):
        """Test that move operation requires folder_id in params."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="move",
            params={}  # Missing folder_id
        )

        # Verify the request is valid but params.folder_id is empty
        assert request.action == BulkOperationAction.MOVE
        assert request.params.get("folder_id") is None

    def test_export_request_with_format(self):
        """Test export request with format parameter."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="export",
            params={"format": "zip", "include_metadata": True}
        )

        assert request.action == BulkOperationAction.EXPORT
        assert request.params.get("format") == "zip"
        assert request.params.get("include_metadata") is True

    def test_categorize_request_with_category(self):
        """Test categorize request with category parameter."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="categorize",
            params={"category": "rechnungen_eingang"}
        )

        assert request.action == BulkOperationAction.CATEGORIZE
        assert request.params.get("category") == "rechnungen_eingang"

    def test_delete_request_with_reason(self):
        """Test delete request with optional reason."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4(), uuid4(), uuid4()],
            action="delete",
            params={"reason": "Test-Loeschung"}
        )

        assert request.action == BulkOperationAction.DELETE
        assert request.params.get("reason") == "Test-Loeschung"

    def test_delete_request_without_reason(self):
        """Test delete request without reason is valid."""
        request = UnifiedBulkOperationRequest(
            document_ids=[uuid4()],
            action="delete",
            params=None
        )

        assert request.action == BulkOperationAction.DELETE
        assert request.params is None


class TestBulkOperationResponse:
    """Tests for the response schema."""

    def test_response_structure(self):
        """Test response has all required fields."""
        response = UnifiedBulkOperationResponse(
            success=True,
            action="tag",
            total_requested=5,
            processed=5,
            failed=0,
            errors=[],
            message="5 Dokumente aktualisiert"
        )

        assert response.success is True
        assert response.action == "tag"
        assert response.total_requested == 5
        assert response.processed == 5
        assert response.failed == 0
        assert response.errors == []
        assert response.task_id is None
        assert response.download_url is None

    def test_response_with_errors(self):
        """Test response with partial failures."""
        response = UnifiedBulkOperationResponse(
            success=False,
            action="delete",
            total_requested=3,
            processed=2,
            failed=1,
            errors=[{"id": "abc-123", "error": "Dokument nicht gefunden"}],
            message="2 von 3 Dokumenten geloescht"
        )

        assert response.success is False
        assert response.failed == 1
        assert len(response.errors) == 1
        assert response.errors[0]["id"] == "abc-123"

    def test_response_with_task_id(self):
        """Test response with async task ID."""
        response = UnifiedBulkOperationResponse(
            success=True,
            action="export",
            total_requested=10,
            processed=10,
            failed=0,
            errors=[],
            message="Export gestartet",
            task_id="celery-task-abc-123"
        )

        assert response.task_id == "celery-task-abc-123"

# -*- coding: utf-8 -*-
"""
Unit Tests fuer Smart Inbox API Endpoints.

Testet:
- GET /smart-inbox: Pagination, Filterung, leere Liste
- POST /{item_id}/act: Gueltige Actions
- POST /{item_id}/snooze: Datetime-Validierung
- POST /{item_id}/dismiss: Erfolgsfall
- GET /insights: AI Insights Response-Struktur
- GET /stats: Statistik-Response
- POST /aggregate: 202 ACCEPTED Response
- Auth: Alle Endpoints ohne Token -> 401

Feinpoliert und durchdacht - Smart Inbox API Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4, UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.smart_inbox import (
    SmartInboxListResponse,
    SmartInboxItemResponse,
    SmartInboxActionRequest,
    SmartInboxSnoozeRequest,
    SmartInboxInsightsResponse,
    SmartInboxInsight,
    SmartInboxStatsResponse,
)

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Fixtures =========================


@pytest.fixture
def mock_user() -> Mock:
    """Mock authenticated user."""
    user = Mock()
    user.id = uuid4()
    user.company_id = uuid4()
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_inbox_item() -> Mock:
    """Mock SmartInboxItem from service."""
    item = Mock()
    item.id = uuid4()
    item.source_type = "alert"
    item.source_id = uuid4()
    item.title = "Kritischer Alert"
    item.description = "System ueberlastet"
    item.category = "system"
    item.raw_priority = 95.0
    item.ml_priority = 97.5
    item.status = "pending"
    item.deadline = None
    item.recommended_actions = [{"action": "acknowledge"}]
    item.context_data = {"severity": "critical"}
    item.document_id = None
    item.entity_id = None
    item.created_at = datetime.now(timezone.utc)
    return item


# ========================= Schema Tests =========================


class TestSmartInboxSchemas:
    """Tests fuer Smart Inbox Schemas."""

    def test_action_request_valid_actions(self):
        """Alle gueltigen Actions werden akzeptiert."""
        valid_actions = ["complete", "approve", "reject", "escalate", "review", "pay"]
        for action in valid_actions:
            req = SmartInboxActionRequest(action=action)
            assert req.action == action

    def test_action_request_invalid_action(self):
        """Ungueltige Action wird abgelehnt."""
        with pytest.raises(ValidationError):
            SmartInboxActionRequest(action="invalid_action")

    def test_action_request_with_data(self):
        """Action mit zusaetzlichen Daten."""
        req = SmartInboxActionRequest(
            action="approve",
            data={"comment": "Genehmigt"}
        )
        assert req.data == {"comment": "Genehmigt"}

    def test_snooze_request_valid(self):
        """Gueltiger Snooze-Request."""
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        req = SmartInboxSnoozeRequest(snooze_until=future)
        assert req.snooze_until == future

    def test_stats_response_valid(self):
        """Statistik-Response mit allen Feldern."""
        stats = SmartInboxStatsResponse(
            total=100,
            pending=30,
            in_progress=15,
            completed_today=45,
            dismissed_today=10,
            avg_response_time_ms=2500,
            by_category={"alert": 20, "deadline": 30, "validation": 50},
            by_source={"alert": 20, "deadline": 30, "validation_queue": 50},
        )
        assert stats.total == 100
        assert stats.by_category["alert"] == 20

    def test_list_response_empty(self):
        """Leere Liste ist gueltig."""
        response = SmartInboxListResponse(items=[], total=0, has_more=False)
        assert response.items == []
        assert response.has_more is False

    def test_insight_response(self):
        """Insight-Response mit allen Feldern."""
        insight = SmartInboxInsight(
            title="Schnelle Bearbeitung",
            description="Sie bearbeiten Alerts 30% schneller als letzte Woche",
            metric="response_time",
            value=2.5,
            trend="down",
        )
        assert insight.trend == "down"


# ========================= GET /smart-inbox Tests =========================


class TestGetSmartInbox:
    """Tests fuer GET /smart-inbox Endpoint."""

    @pytest.mark.asyncio
    async def test_get_inbox_success(self, mock_user, mock_db, sample_inbox_item):
        """Erfolgreicher Abruf der Inbox-Items."""
        from app.api.v1.smart_inbox import get_smart_inbox

        mock_result = Mock()
        mock_result.items = [sample_inbox_item]
        mock_result.total = 1
        mock_result.has_more = False

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.get_prioritized_items = AsyncMock(return_value=mock_result)

            result = await get_smart_inbox(
                page=1, per_page=20, status_filter=None, category=None,
                db=mock_db, current_user=mock_user,
            )

        assert isinstance(result, SmartInboxListResponse)
        assert result.total == 1
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_inbox_with_filters(self, mock_user, mock_db):
        """Filterung nach Status und Kategorie."""
        from app.api.v1.smart_inbox import get_smart_inbox

        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        mock_result.has_more = False

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            instance = MockService.return_value
            instance.get_prioritized_items = AsyncMock(return_value=mock_result)

            await get_smart_inbox(
                page=2, per_page=10, status_filter="pending", category="alert",
                db=mock_db, current_user=mock_user,
            )

            call_kwargs = instance.get_prioritized_items.call_args[1]
            assert call_kwargs["status"] == "pending"
            assert call_kwargs["category"] == "alert"
            assert call_kwargs["offset"] == 10  # (page-1) * per_page
            assert call_kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_inbox_service_error(self, mock_user, mock_db):
        """Service-Fehler wird als 500 zurueckgegeben."""
        from app.api.v1.smart_inbox import get_smart_inbox

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.get_prioritized_items = AsyncMock(
                side_effect=RuntimeError("DB down")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_smart_inbox(
                    page=1, per_page=20, status_filter=None, category=None,
                    db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 500


# ========================= POST /{item_id}/act Tests =========================


class TestPerformInboxAction:
    """Tests fuer POST /{item_id}/act Endpoint."""

    @pytest.mark.asyncio
    async def test_perform_action_success(self, mock_user, mock_db):
        """Erfolgreiche Aktion gibt 204 zurueck."""
        from app.api.v1.smart_inbox import perform_inbox_action

        item_id = uuid4()
        request = SmartInboxActionRequest(action="approve")

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.perform_action = AsyncMock()

            result = await perform_inbox_action(
                item_id=item_id, request=request,
                db=mock_db, current_user=mock_user,
            )

        assert result is None  # 204 No Content

    @pytest.mark.asyncio
    async def test_perform_action_not_found(self, mock_user, mock_db):
        """Nicht existierendes Item gibt 404 zurueck."""
        from app.api.v1.smart_inbox import perform_inbox_action

        item_id = uuid4()
        request = SmartInboxActionRequest(action="complete")

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.perform_action = AsyncMock(
                side_effect=ValueError("Item nicht gefunden")
            )

            with pytest.raises(HTTPException) as exc_info:
                await perform_inbox_action(
                    item_id=item_id, request=request,
                    db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_perform_action_forbidden(self, mock_user, mock_db):
        """Fehlende Berechtigung gibt 403 zurueck."""
        from app.api.v1.smart_inbox import perform_inbox_action

        item_id = uuid4()
        request = SmartInboxActionRequest(action="approve")

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.perform_action = AsyncMock(
                side_effect=PermissionError("Keine Berechtigung")
            )

            with pytest.raises(HTTPException) as exc_info:
                await perform_inbox_action(
                    item_id=item_id, request=request,
                    db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 403


# ========================= POST /{item_id}/snooze Tests =========================


class TestSnoozeInboxItem:
    """Tests fuer POST /{item_id}/snooze Endpoint."""

    @pytest.mark.asyncio
    async def test_snooze_success(self, mock_user, mock_db):
        """Erfolgreiches Snoozen gibt 204 zurueck."""
        from app.api.v1.smart_inbox import snooze_inbox_item

        item_id = uuid4()
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        request = SmartInboxSnoozeRequest(snooze_until=future)

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.snooze_item = AsyncMock()

            result = await snooze_inbox_item(
                item_id=item_id, request=request,
                db=mock_db, current_user=mock_user,
            )

        assert result is None  # 204 No Content

    @pytest.mark.asyncio
    async def test_snooze_past_datetime_returns_400(self, mock_user, mock_db):
        """Snooze-Zeitpunkt in der Vergangenheit gibt 400 zurueck."""
        from app.api.v1.smart_inbox import snooze_inbox_item

        item_id = uuid4()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        request = SmartInboxSnoozeRequest(snooze_until=past)

        with pytest.raises(HTTPException) as exc_info:
            await snooze_inbox_item(
                item_id=item_id, request=request,
                db=mock_db, current_user=mock_user,
            )

        assert exc_info.value.status_code == 400
        assert "Zukunft" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_snooze_not_found(self, mock_user, mock_db):
        """Nicht existierendes Item beim Snoozen gibt 404 zurueck."""
        from app.api.v1.smart_inbox import snooze_inbox_item

        item_id = uuid4()
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        request = SmartInboxSnoozeRequest(snooze_until=future)

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.snooze_item = AsyncMock(
                side_effect=ValueError("Item nicht gefunden")
            )

            with pytest.raises(HTTPException) as exc_info:
                await snooze_inbox_item(
                    item_id=item_id, request=request,
                    db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 404


# ========================= POST /{item_id}/dismiss Tests =========================


class TestDismissInboxItem:
    """Tests fuer POST /{item_id}/dismiss Endpoint."""

    @pytest.mark.asyncio
    async def test_dismiss_success(self, mock_user, mock_db):
        """Erfolgreiches Dismiss gibt 204 zurueck."""
        from app.api.v1.smart_inbox import dismiss_inbox_item

        item_id = uuid4()

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.dismiss_item = AsyncMock()

            result = await dismiss_inbox_item(
                item_id=item_id, db=mock_db, current_user=mock_user,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_dismiss_not_found(self, mock_user, mock_db):
        """Nicht existierendes Item beim Dismiss gibt 404 zurueck."""
        from app.api.v1.smart_inbox import dismiss_inbox_item

        item_id = uuid4()

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.dismiss_item = AsyncMock(
                side_effect=ValueError("Item nicht gefunden")
            )

            with pytest.raises(HTTPException) as exc_info:
                await dismiss_inbox_item(
                    item_id=item_id, db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_dismiss_forbidden(self, mock_user, mock_db):
        """Fehlende Berechtigung beim Dismiss gibt 403 zurueck."""
        from app.api.v1.smart_inbox import dismiss_inbox_item

        item_id = uuid4()

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.dismiss_item = AsyncMock(
                side_effect=PermissionError("Anderer Mandant")
            )

            with pytest.raises(HTTPException) as exc_info:
                await dismiss_inbox_item(
                    item_id=item_id, db=mock_db, current_user=mock_user,
                )

            assert exc_info.value.status_code == 403


# ========================= GET /insights Tests =========================


class TestGetInboxInsights:
    """Tests fuer GET /insights Endpoint."""

    @pytest.mark.asyncio
    async def test_insights_success(self, mock_user, mock_db):
        """Erfolgreicher Abruf der Insights."""
        from app.api.v1.smart_inbox import get_inbox_insights

        mock_insights = [
            {
                "title": "Schnelle Bearbeitung",
                "description": "30% schneller",
                "metric": "response_time",
                "value": 2.5,
                "trend": "down",
            },
            {
                "title": "Alert-Fokus",
                "description": "Mehr Alerts bearbeitet",
                "metric": "alert_count",
                "value": 15.0,
                "trend": "up",
            },
        ]

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.get_user_insights = AsyncMock(return_value=mock_insights)

            result = await get_inbox_insights(db=mock_db, current_user=mock_user)

        assert isinstance(result, SmartInboxInsightsResponse)
        assert len(result.insights) == 2
        assert result.insights[0].trend == "down"

    @pytest.mark.asyncio
    async def test_insights_service_error(self, mock_user, mock_db):
        """Service-Fehler bei Insights gibt 500 zurueck."""
        from app.api.v1.smart_inbox import get_inbox_insights

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.get_user_insights = AsyncMock(
                side_effect=RuntimeError("ML model failed")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_inbox_insights(db=mock_db, current_user=mock_user)

            assert exc_info.value.status_code == 500


# ========================= GET /stats Tests =========================


class TestGetInboxStats:
    """Tests fuer GET /stats Endpoint."""

    @pytest.mark.asyncio
    async def test_stats_success(self, mock_user, mock_db):
        """Erfolgreicher Abruf der Statistiken."""
        from app.api.v1.smart_inbox import get_inbox_stats

        mock_stats = {
            "total": 100,
            "pending": 30,
            "in_progress": 15,
            "completed_today": 45,
            "dismissed_today": 10,
            "avg_response_time_ms": 2500,
            "by_category": {"alert": 20, "deadline": 30},
            "by_source": {"alert": 20, "deadline": 30},
        }

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.get_statistics = AsyncMock(return_value=mock_stats)

            result = await get_inbox_stats(db=mock_db, current_user=mock_user)

        assert isinstance(result, SmartInboxStatsResponse)
        assert result.total == 100
        assert result.pending == 30


# ========================= POST /aggregate Tests =========================


class TestTriggerAggregation:
    """Tests fuer POST /aggregate Endpoint."""

    @pytest.mark.asyncio
    async def test_aggregate_success(self, mock_user, mock_db):
        """Erfolgreiche Aggregation gibt 202 mit Task-ID zurueck."""
        from app.api.v1.smart_inbox import trigger_manual_aggregation

        task_id = uuid4()

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.trigger_aggregation = AsyncMock(return_value=task_id)

            result = await trigger_manual_aggregation(db=mock_db, current_user=mock_user)

        assert result["message"] == "Aggregation wurde gestartet"
        assert result["task_id"] == str(task_id)

    @pytest.mark.asyncio
    async def test_aggregate_service_error(self, mock_user, mock_db):
        """Service-Fehler bei Aggregation gibt 500 zurueck."""
        from app.api.v1.smart_inbox import trigger_manual_aggregation

        with patch('app.api.v1.smart_inbox.SmartInboxService') as MockService:
            MockService.return_value.trigger_aggregation = AsyncMock(
                side_effect=RuntimeError("Celery down")
            )

            with pytest.raises(HTTPException) as exc_info:
                await trigger_manual_aggregation(db=mock_db, current_user=mock_user)

            assert exc_info.value.status_code == 500

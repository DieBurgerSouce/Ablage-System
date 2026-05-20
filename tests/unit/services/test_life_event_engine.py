# -*- coding: utf-8 -*-
"""Unit tests for Life Event Engine Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import date, datetime, timezone

from app.services.privat.life_events.life_event_engine import (
    LifeEventEngine,
    EVENT_TYPES,
)
from app.db.models import LifeEvent


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Life event engine instance."""
    return LifeEventEngine(db=mock_db)


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid4()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.mark.asyncio
async def test_create_life_event_umzug(service, mock_db, user_id, company_id):
    """Test creating a moving (Umzug) event."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="umzug",
        event_date=datetime(2026, 2, 1),
        notes="Umzug nach München",
    )

    assert isinstance(event, LifeEvent)
    assert event.event_type == "umzug"
    assert event.title == "Umzug"
    assert event.description == "Umzug nach München"
    assert event.status == "confirmed"
    assert len(event.checklist) > 0
    assert len(event.recommendations) >= 0

    # Verify checklist items
    checklist_ids = [item["id"] for item in event.checklist]
    assert "ummeldung" in checklist_ids
    assert "post_nachsendung" in checklist_ids

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_life_event_heirat(service, mock_db, user_id, company_id):
    """Test creating a marriage (Heirat) event."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="heirat",
        event_date=datetime(2026, 6, 15),
    )

    assert event.event_type == "heirat"
    assert event.title == "Heirat"
    assert len(event.checklist) > 0

    # Verify marriage-specific checklist items
    checklist_ids = [item["id"] for item in event.checklist]
    assert "standesamt" in checklist_ids
    assert "steuerklasse" in checklist_ids


@pytest.mark.asyncio
async def test_create_life_event_kind(service, mock_db, user_id, company_id):
    """Test creating a child birth (Kind) event."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="kind",
        event_date=datetime(2026, 3, 10),
    )

    assert event.event_type == "kind"
    assert event.title == "Geburt eines Kindes"
    assert len(event.checklist) > 0

    # Verify child-specific checklist items
    checklist_ids = [item["id"] for item in event.checklist]
    assert "geburtsurkunde" in checklist_ids
    assert "elterngeld" in checklist_ids
    assert "kindergeld" in checklist_ids


@pytest.mark.asyncio
async def test_create_life_event_immobilienkauf(service, mock_db, user_id, company_id):
    """Test creating a property purchase (Immobilienkauf) event."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="immobilienkauf",
        event_date=datetime(2026, 5, 20),
    )

    assert event.event_type == "immobilienkauf"
    assert event.title == "Immobilienkauf"

    # Verify property-specific checklist items
    checklist_ids = [item["id"] for item in event.checklist]
    assert "finanzierung" in checklist_ids
    assert "notar" in checklist_ids
    assert "grunderwerbsteuer" in checklist_ids


@pytest.mark.asyncio
async def test_get_life_events_for_user(service, mock_db, user_id, company_id):
    """Test retrieving all life events for a user."""
    # Mock life events
    mock_event1 = MagicMock(spec=LifeEvent)
    mock_event1.id = uuid4()
    mock_event1.event_type = "umzug"
    mock_event1.event_date = datetime(2026, 1, 1).date()

    mock_event2 = MagicMock(spec=LifeEvent)
    mock_event2.id = uuid4()
    mock_event2.event_type = "heirat"
    mock_event2.event_date = datetime(2026, 6, 1).date()

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_event1, mock_event2]
    mock_db.execute.return_value = mock_result

    events = await service.get_life_events(
        user_id=user_id,
        company_id=company_id,
    )

    assert len(events) == 2
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_checklist_item(service, mock_db, user_id, company_id):
    """Test marking a checklist item as complete."""
    event_id = uuid4()

    # Mock life event
    mock_event = MagicMock(spec=LifeEvent)
    mock_event.id = event_id
    mock_event.checklist = [
        {"id": "ummeldung", "label": "Ummeldung", "done": False},
        {"id": "post_nachsendung", "label": "Post", "done": False},
    ]
    mock_event.status = "confirmed"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    updated = await service.update_checklist_item(
        event_id=event_id,
        company_id=company_id,
        item_id="ummeldung",
        done=True,
    )

    assert updated is not None
    # Find the updated item
    ummeldung_item = next(
        item for item in updated.checklist if item["id"] == "ummeldung"
    )
    assert ummeldung_item["done"] is True
    assert "completed_at" in ummeldung_item

    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_complete_life_event(service, mock_db, user_id, company_id):
    """Test marking a life event as completed."""
    event_id = uuid4()

    # Mock life event
    mock_event = MagicMock(spec=LifeEvent)
    mock_event.id = event_id
    mock_event.status = "in_progress"
    mock_event.completed_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    completed = await service.complete_life_event(
        event_id=event_id,
        company_id=company_id,
    )

    assert completed is not None
    assert completed.status == "completed"
    assert completed.completed_at is not None
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_get_event_types(service):
    """Test retrieving all available event types."""
    event_types = await service.get_event_types()

    assert isinstance(event_types, dict)
    assert len(event_types) == 8  # 8 event types defined

    # Check for specific event types
    assert "umzug" in event_types
    assert "heirat" in event_types
    assert "kind" in event_types
    assert "jobwechsel" in event_types
    assert "ruhestand" in event_types
    assert "todesfall" in event_types
    assert "immobilienkauf" in event_types
    assert "scheidung" in event_types

    # Check structure
    for event_type, info in event_types.items():
        assert "label" in info
        assert "description" in info
        assert "icon" in info


@pytest.mark.asyncio
async def test_get_active_events_count(service, mock_db, user_id, company_id):
    """Test counting active life events."""
    # Mock count result
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 3
    mock_db.execute.return_value = mock_result

    count = await service.get_active_events_count(
        user_id=user_id,
        company_id=company_id,
    )

    assert count == 3
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_checklist_templates(service):
    """Test each event type has correct checklist template."""
    event_types_to_test = [
        "umzug",
        "heirat",
        "kind",
        "jobwechsel",
        "ruhestand",
        "todesfall",
        "immobilienkauf",
        "scheidung",
    ]

    for event_type in event_types_to_test:
        # Import the template function
        from app.services.privat.life_events.life_event_engine import (
            _get_checklist_template,
        )

        checklist = _get_checklist_template(event_type)

        assert isinstance(checklist, list)
        assert len(checklist) > 0

        # Verify each item has required fields
        for item in checklist:
            assert "id" in item
            assert "label" in item
            assert "category" in item
            assert "priority" in item
            assert "done" in item


@pytest.mark.asyncio
async def test_financial_impact_estimation(service, mock_db, user_id, company_id):
    """Test financial impact cost ranges are calculated."""
    # Test different event types
    event_types_with_costs = ["umzug", "heirat", "kind", "immobilienkauf"]

    for event_type in event_types_with_costs:
        event = await service.create_life_event(
            user_id=user_id,
            company_id=company_id,
            event_type=event_type,
            event_date=datetime(2026, 1, 1),
        )

        assert "financial_impact" in event.__dict__ or hasattr(
            event, "financial_impact"
        )
        if hasattr(event, "financial_impact"):
            impact = event.financial_impact
            assert "estimated_cost_min" in impact
            assert "estimated_cost_max" in impact
            assert impact["estimated_cost_min"] >= 0
            assert impact["estimated_cost_max"] >= impact["estimated_cost_min"]


@pytest.mark.asyncio
async def test_recommendations(service, mock_db, user_id, company_id):
    """Test event-specific advice is generated."""
    # Test event types with recommendations
    event_types_with_recs = ["umzug", "heirat", "kind", "jobwechsel"]

    for event_type in event_types_with_recs:
        event = await service.create_life_event(
            user_id=user_id,
            company_id=company_id,
            event_type=event_type,
            event_date=datetime(2026, 1, 1),
        )

        # Recommendations might be empty list for some types
        assert isinstance(event.recommendations, list)


@pytest.mark.asyncio
async def test_auto_complete_when_all_items_done(service, mock_db, company_id):
    """Test event auto-completes when all checklist items are done."""
    event_id = uuid4()

    # Mock life event with one uncompleted item
    mock_event = MagicMock(spec=LifeEvent)
    mock_event.id = event_id
    mock_event.checklist = [
        {"id": "item1", "done": True},
        {"id": "item2", "done": False},  # Last item
    ]
    mock_event.status = "confirmed"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    # Mark last item as done
    updated = await service.update_checklist_item(
        event_id=event_id,
        company_id=company_id,
        item_id="item2",
        done=True,
    )

    # Should auto-complete
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_filter_by_status(service, mock_db, user_id, company_id):
    """Test filtering life events by status."""
    # Mock events with different statuses
    confirmed_event = MagicMock(spec=LifeEvent)
    confirmed_event.status = "confirmed"

    completed_event = MagicMock(spec=LifeEvent)
    completed_event.status = "completed"

    # Only return confirmed when filtered
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [confirmed_event]
    mock_db.execute.return_value = mock_result

    events = await service.get_life_events(
        user_id=user_id,
        company_id=company_id,
        status_filter="confirmed",
    )

    assert len(events) == 1
    assert events[0].status == "confirmed"


@pytest.mark.asyncio
async def test_invalid_event_type(service, user_id, company_id):
    """Test error when creating event with invalid type."""
    with pytest.raises(ValueError, match="Unbekannter Event-Typ"):
        await service.create_life_event(
            user_id=user_id,
            company_id=company_id,
            event_type="invalid_type",
            event_date=datetime(2026, 1, 1),
        )


@pytest.mark.asyncio
async def test_get_single_life_event(service, mock_db, company_id):
    """Test retrieving a single life event by ID."""
    event_id = uuid4()

    # Mock life event
    mock_event = MagicMock(spec=LifeEvent)
    mock_event.id = event_id
    mock_event.event_type = "umzug"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_event
    mock_db.execute.return_value = mock_result

    event = await service.get_life_event(
        event_id=event_id,
        company_id=company_id,
    )

    assert event is not None
    assert event.id == event_id
    assert event.event_type == "umzug"


@pytest.mark.asyncio
async def test_checklist_item_priorities(service, mock_db, user_id, company_id):
    """Test checklist items have priority levels."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="umzug",
        event_date=datetime(2026, 1, 1),
    )

    # All items should have priority
    for item in event.checklist:
        assert "priority" in item
        assert item["priority"] in ["high", "medium", "low"]


@pytest.mark.asyncio
async def test_default_event_date(service, mock_db, user_id, company_id):
    """Test event defaults to today if no date provided."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="umzug",
        event_date=None,  # No date provided
    )

    # Should default to today
    assert event.event_date is not None
    assert isinstance(event.event_date, date)


@pytest.mark.asyncio
async def test_detection_source_manual(service, mock_db, user_id, company_id):
    """Test manually created events have detection_source='manual'."""
    event = await service.create_life_event(
        user_id=user_id,
        company_id=company_id,
        event_type="heirat",
        event_date=datetime(2026, 6, 1),
    )

    assert event.detection_source == "manual"

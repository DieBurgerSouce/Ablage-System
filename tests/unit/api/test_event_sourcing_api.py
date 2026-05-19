# -*- coding: utf-8 -*-
"""Unit-Tests fuer K6: event_sourcing.py aggregate_type Whitelist.

Vor dem Fix wurden beliebige Strings als aggregate_type-Pfadparameter
an den EventStore weitergereicht (Injection-Vektor, IDOR-Enumeration).

Nach dem Fix:
- _validate_aggregate_type wirft 400 bei unbekanntem Typ
- get_events, get_snapshot, get_projection validieren VOR Service-Call
- Bekannte Typen passieren durch zur Service-Schicht

Feinpoliert und durchdacht - Injection-Guard fuer Event-Sourcing-API.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.v1.event_sourcing import (
    ALLOWED_AGGREGATE_TYPES,
    _validate_aggregate_type,
)


pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Fixtures =========================


@pytest.fixture
def user():
    u = Mock()
    u.id = uuid4()
    u.company_id = uuid4()
    return u


@pytest.fixture
def mock_db():
    return AsyncMock()


# ========================= _validate_aggregate_type =========================


class TestAggregateTypeWhitelist:
    """K6: _validate_aggregate_type Whitelist-Pruefung."""

    def test_allowed_types_pass(self):
        for t in ALLOWED_AGGREGATE_TYPES:
            _validate_aggregate_type(t)  # should not raise

    def test_unknown_type_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_aggregate_type("malicious_type")
        assert exc.value.status_code == 400
        assert "aggregate_type" in exc.value.detail.lower()

    def test_sql_injection_string_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_aggregate_type("'; DROP TABLE events; --")
        assert exc.value.status_code == 400

    def test_path_traversal_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_aggregate_type("../../../etc/passwd")
        assert exc.value.status_code == 400

    def test_empty_string_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_aggregate_type("")
        assert exc.value.status_code == 400

    def test_case_sensitive(self):
        """Whitelist ist case-sensitive - DOCUMENT in Caps ist NICHT erlaubt."""
        with pytest.raises(HTTPException):
            _validate_aggregate_type("DOCUMENT")

    def test_whitelist_matches_snapshot_service(self):
        """Router-Whitelist MUSS Subset/Match von Snapshot-Service-Whitelist sein."""
        expected = {"document", "invoice", "payment", "entity", "alert", "workflow"}
        assert ALLOWED_AGGREGATE_TYPES == expected


# ========================= Endpoint-Integration =========================


class TestGetEventsValidation:
    """get_events validiert VOR EventStore-Call."""

    async def test_invalid_aggregate_type_raises_400_before_service(
        self, user, mock_db
    ):
        # Wenn EventStore aufgerufen wuerde, wuerde der Mock einen Side-Effect
        # ausloesen. Da die Whitelist VOR Service-Call greift, darf der Service
        # NICHT erreicht werden.
        called = []

        class FakeStore:
            async def get_events(self, **kwargs):
                called.append(kwargs)
                return []

        with patch("app.api.v1.event_sourcing.EventStore", FakeStore):
            from app.api.v1.event_sourcing import get_events

            with pytest.raises(HTTPException) as exc:
                await get_events(
                    aggregate_type="evil_type",
                    aggregate_id=uuid4(),
                    after_sequence=0,
                    current_user=user,
                    db=mock_db,
                )
        assert exc.value.status_code == 400
        # EventStore.get_events darf NICHT aufgerufen worden sein
        assert called == [], "EventStore wurde trotz invalid aggregate_type aufgerufen"

    async def test_valid_aggregate_type_reaches_service(self, user, mock_db):
        called = []

        class FakeStore:
            async def get_events(self, **kwargs):
                called.append(kwargs)
                return []

        with patch("app.api.v1.event_sourcing.EventStore", FakeStore):
            from app.api.v1.event_sourcing import get_events

            result = await get_events(
                aggregate_type="document",
                aggregate_id=uuid4(),
                after_sequence=0,
                current_user=user,
                db=mock_db,
            )
        assert result == []
        assert len(called) == 1
        assert called[0]["aggregate_type"] == "document"


class TestGetSnapshotValidation:
    async def test_invalid_aggregate_type_raises_400_before_service(
        self, user, mock_db
    ):
        called = []

        class FakeSvc:
            async def get_latest_snapshot(self, **kwargs):
                called.append(kwargs)
                return None

        with patch("app.api.v1.event_sourcing.SnapshotService", FakeSvc):
            from app.api.v1.event_sourcing import get_snapshot

            with pytest.raises(HTTPException) as exc:
                await get_snapshot(
                    aggregate_type="'; DROP TABLE snapshots --",
                    aggregate_id=uuid4(),
                    current_user=user,
                    db=mock_db,
                )
        assert exc.value.status_code == 400
        assert called == []


class TestGetProjectionValidation:
    async def test_invalid_aggregate_type_raises_400_before_service(
        self, user, mock_db
    ):
        called = []

        class FakeProj:
            async def project(self, **kwargs):
                called.append(("project", kwargs))
                return {}

            async def project_at_sequence(self, **kwargs):
                called.append(("project_at_sequence", kwargs))
                return {}

        class FakeStore:
            async def get_event_count(self, **kwargs):
                called.append(("get_event_count", kwargs))
                return 0

            async def get_events(self, **kwargs):
                called.append(("get_events", kwargs))
                return []

        with patch("app.api.v1.event_sourcing.ProjectionService", FakeProj), patch(
            "app.api.v1.event_sourcing.EventStore", FakeStore
        ):
            from app.api.v1.event_sourcing import get_projection

            with pytest.raises(HTTPException) as exc:
                await get_projection(
                    aggregate_type="../etc/passwd",
                    aggregate_id=uuid4(),
                    at_sequence=None,
                    current_user=user,
                    db=mock_db,
                )
        assert exc.value.status_code == 400
        assert called == []

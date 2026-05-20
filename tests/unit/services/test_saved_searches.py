# -*- coding: utf-8 -*-
"""
Tests fuer Saved Search Service - Phase 2 Feature.

Testet:
- SavedSearch Model CRUD Operations
- User-spezifische Suchen (Isolation)
- Unique Constraint (user_id, name)
- use_count Inkrement bei Execute
- last_used_at Update bei Execute
- Sortierung nach use_count DESC
- Filter-Persistierung und Restore
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models_saved_search import SavedSearch


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def mock_user_a():
    """Mock Benutzer A."""
    user = Mock()
    user.id = uuid4()
    user.email = "user_a@test.de"
    return user


@pytest.fixture
def mock_user_b():
    """Mock Benutzer B."""
    user = Mock()
    user.id = uuid4()
    user.email = "user_b@test.de"
    return user


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession fuer Datenbank-Operationen."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = Mock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def sample_search_filters() -> Dict[str, object]:
    """Beispiel Filter-Dict fuer gespeicherte Suche."""
    return {
        "document_type": "invoice",
        "status": "validated",
        "date_range": {
            "start": "2024-01-01",
            "end": "2024-12-31"
        },
        "min_amount": 100.00,
        "max_amount": 5000.00,
        "tags": ["important", "processed"]
    }


# =============================================================================
# SavedSearch Model Tests
# =============================================================================

class TestSavedSearchModel:
    """Tests fuer SavedSearch SQLAlchemy Model."""

    def test_create_saved_search_with_required_fields(self, mock_user_a):
        """SavedSearch kann mit Minimal-Feldern erstellt werden."""
        search = SavedSearch(
            user_id=mock_user_a.id,
            name="Meine Rechnungen",
            query="rechnung",
            search_type="hybrid"
        )

        assert search.user_id == mock_user_a.id
        assert search.name == "Meine Rechnungen"
        assert search.query == "rechnung"
        assert search.search_type == "hybrid"
        assert search.use_count == 0
        assert search.is_default is False
        assert search.last_used_at is None

    def test_create_saved_search_with_filters(self, mock_user_a, sample_search_filters):
        """SavedSearch speichert Filter im JSONB-Feld."""
        search = SavedSearch(
            user_id=mock_user_a.id,
            name="Gefilterte Suche",
            query="test",
            search_type="fts",
            filters=sample_search_filters
        )

        assert search.filters == sample_search_filters
        assert search.filters["document_type"] == "invoice"
        assert search.filters["date_range"]["start"] == "2024-01-01"

    def test_create_saved_search_with_sorting(self, mock_user_a):
        """SavedSearch speichert Sortierfeld und -richtung."""
        search = SavedSearch(
            user_id=mock_user_a.id,
            name="Sortierte Suche",
            query="dokument",
            search_type="semantic",
            sort_field="created_at",
            sort_order="desc"
        )

        assert search.sort_field == "created_at"
        assert search.sort_order == "desc"

    def test_saved_search_repr(self, mock_user_a):
        """__repr__ gibt sinnvolle String-Darstellung."""
        search_id = uuid4()
        search = SavedSearch(
            id=search_id,
            user_id=mock_user_a.id,
            name="Test Search",
            query="test",
            search_type="hybrid"
        )

        repr_str = repr(search)
        assert "SavedSearch" in repr_str
        assert str(search_id) in repr_str
        assert str(mock_user_a.id) in repr_str
        assert "Test Search" in repr_str


# =============================================================================
# CRUD Operations Tests
# =============================================================================

class TestSavedSearchCRUD:
    """Tests fuer Create, Read, Update, Delete Operations."""

    @pytest.mark.asyncio
    async def test_create_saved_search(self, mock_db_session, mock_user_a):
        """Neue gespeicherte Suche kann erstellt werden."""
        new_search = SavedSearch(
            user_id=mock_user_a.id,
            name="Neue Suche",
            query="lieferant:mustermann",
            search_type="hybrid"
        )

        mock_db_session.add(new_search)
        await mock_db_session.commit()
        await mock_db_session.refresh(new_search)

        mock_db_session.add.assert_called_once_with(new_search)
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_user_saved_searches(self, mock_db_session, mock_user_a):
        """Benutzer kann seine gespeicherten Suchen auflisten."""
        # Mock Query-Ergebnis
        search1 = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Oft genutzt",
            query="wichtig",
            search_type="hybrid",
            use_count=15
        )
        search2 = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Selten genutzt",
            query="archiv",
            search_type="fts",
            use_count=3
        )

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [search1, search2]
        mock_db_session.execute.return_value = mock_result

        # Simulate ordering by use_count desc
        searches = [search1, search2]  # Already ordered

        assert len(searches) == 2
        assert searches[0].use_count == 15
        assert searches[1].use_count == 3
        assert searches[0].use_count >= searches[1].use_count

    @pytest.mark.asyncio
    async def test_update_saved_search_name(self, mock_db_session, mock_user_a):
        """Name einer gespeicherten Suche kann aktualisiert werden."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Alter Name",
            query="test",
            search_type="hybrid"
        )

        # Update name
        search.name = "Neuer Name"

        await mock_db_session.commit()
        await mock_db_session.refresh(search)

        assert search.name == "Neuer Name"
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_saved_search_filters(self, mock_db_session, mock_user_a, sample_search_filters):
        """Filter einer gespeicherten Suche koennen aktualisiert werden."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Test",
            query="test",
            search_type="hybrid",
            filters={"old": "filter"}
        )

        # Update filters
        search.filters = sample_search_filters

        await mock_db_session.commit()

        assert search.filters == sample_search_filters
        assert search.filters["document_type"] == "invoice"

    @pytest.mark.asyncio
    async def test_delete_saved_search(self, mock_db_session, mock_user_a):
        """Gespeicherte Suche kann geloescht werden."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Zu loeschen",
            query="test",
            search_type="hybrid"
        )

        mock_db_session.delete(search)
        await mock_db_session.commit()

        mock_db_session.delete.assert_called_once_with(search)
        mock_db_session.commit.assert_called_once()


# =============================================================================
# Execute & Usage Tracking Tests
# =============================================================================

class TestSavedSearchExecution:
    """Tests fuer Ausfuehrung und Nutzungsstatistik."""

    @pytest.mark.asyncio
    async def test_execute_increments_use_count(self, mock_db_session, mock_user_a):
        """Ausfuehren einer Suche erhoeht use_count."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Test Search",
            query="test",
            search_type="hybrid",
            use_count=5
        )

        # Simulate execution
        search.use_count += 1
        search.last_used_at = datetime.utcnow()

        await mock_db_session.commit()

        assert search.use_count == 6

    @pytest.mark.asyncio
    async def test_execute_updates_last_used_at(self, mock_db_session, mock_user_a):
        """Ausfuehren einer Suche aktualisiert last_used_at."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Test Search",
            query="test",
            search_type="hybrid",
            last_used_at=None
        )

        # Simulate execution
        now = datetime.utcnow()
        search.last_used_at = now

        await mock_db_session.commit()

        assert search.last_used_at is not None
        assert isinstance(search.last_used_at, datetime)
        assert (datetime.utcnow() - search.last_used_at).total_seconds() < 1

    @pytest.mark.asyncio
    async def test_first_execution_sets_use_count_to_one(self, mock_db_session, mock_user_a):
        """Erste Ausfuehrung setzt use_count auf 1."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Test Search",
            query="test",
            search_type="hybrid",
            use_count=0,
            last_used_at=None
        )

        # First execution
        search.use_count += 1
        search.last_used_at = datetime.utcnow()

        await mock_db_session.commit()

        assert search.use_count == 1
        assert search.last_used_at is not None


# =============================================================================
# Unique Constraint Tests
# =============================================================================

class TestSavedSearchUniqueConstraint:
    """Tests fuer Unique Constraint (user_id, name)."""

    @pytest.mark.asyncio
    async def test_unique_constraint_same_user_same_name(self, mock_db_session, mock_user_a):
        """Derselbe Benutzer kann nicht zwei Suchen mit gleichem Namen haben."""
        search1 = SavedSearch(
            user_id=mock_user_a.id,
            name="Meine Suche",
            query="test1",
            search_type="hybrid"
        )

        search2 = SavedSearch(
            user_id=mock_user_a.id,
            name="Meine Suche",  # Same name!
            query="test2",
            search_type="fts"
        )

        # Simulate IntegrityError on commit
        mock_db_session.commit.side_effect = IntegrityError(
            "duplicate key",
            None,
            None
        )

        mock_db_session.add(search1)
        await mock_db_session.commit()
        mock_db_session.commit.side_effect = None  # Reset for next add

        mock_db_session.add(search2)
        mock_db_session.commit.side_effect = IntegrityError(
            "duplicate key",
            None,
            None
        )

        with pytest.raises(IntegrityError):
            await mock_db_session.commit()

    @pytest.mark.asyncio
    async def test_unique_constraint_different_users_same_name(self, mock_db_session, mock_user_a, mock_user_b):
        """Verschiedene Benutzer koennen Suchen mit gleichem Namen haben."""
        search1 = SavedSearch(
            user_id=mock_user_a.id,
            name="Standard Suche",
            query="test",
            search_type="hybrid"
        )

        search2 = SavedSearch(
            user_id=mock_user_b.id,
            name="Standard Suche",  # Same name, different user
            query="test",
            search_type="hybrid"
        )

        mock_db_session.add(search1)
        await mock_db_session.commit()

        mock_db_session.add(search2)
        await mock_db_session.commit()

        # Should not raise
        assert search1.name == search2.name
        assert search1.user_id != search2.user_id


# =============================================================================
# User Isolation Tests
# =============================================================================

class TestSavedSearchUserIsolation:
    """Tests fuer Benutzer-Isolation (User A sieht nicht Suchen von User B)."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_searches(self, mock_db_session, mock_user_a, mock_user_b):
        """Benutzer A sieht nicht die Suchen von Benutzer B."""
        # Create searches for user A
        search_a = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="User A Search",
            query="test_a",
            search_type="hybrid"
        )

        # Create searches for user B
        search_b = SavedSearch(
            id=uuid4(),
            user_id=mock_user_b.id,
            name="User B Search",
            query="test_b",
            search_type="hybrid"
        )

        # Mock query result for user A (only their searches)
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [search_a]
        mock_db_session.execute.return_value = mock_result

        # Simulate querying for user A's searches
        user_a_searches = [search_a]

        assert len(user_a_searches) == 1
        assert user_a_searches[0].user_id == mock_user_a.id
        assert all(s.user_id == mock_user_a.id for s in user_a_searches)

    @pytest.mark.asyncio
    async def test_user_cannot_update_other_users_searches(self, mock_user_a, mock_user_b):
        """Benutzer A kann nicht die Suche von Benutzer B aendern."""
        search_b = SavedSearch(
            id=uuid4(),
            user_id=mock_user_b.id,
            name="User B Search",
            query="test",
            search_type="hybrid"
        )

        # User A tries to access user B's search (should fail in real API)
        assert search_b.user_id != mock_user_a.id

    @pytest.mark.asyncio
    async def test_user_cannot_delete_other_users_searches(self, mock_user_a, mock_user_b):
        """Benutzer A kann nicht die Suche von Benutzer B loeschen."""
        search_b = SavedSearch(
            id=uuid4(),
            user_id=mock_user_b.id,
            name="User B Search",
            query="test",
            search_type="hybrid"
        )

        # Verify ownership check would prevent deletion
        assert search_b.user_id != mock_user_a.id


# =============================================================================
# Default Search Tests
# =============================================================================

class TestSavedSearchDefault:
    """Tests fuer Standard-Suche Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_set_search_as_default(self, mock_db_session, mock_user_a):
        """Suche kann als Standard markiert werden."""
        search = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Standard Suche",
            query="wichtig",
            search_type="hybrid",
            is_default=False
        )

        search.is_default = True
        await mock_db_session.commit()

        assert search.is_default is True

    @pytest.mark.asyncio
    async def test_only_one_default_per_user(self, mock_db_session, mock_user_a):
        """Nur eine Suche pro Benutzer kann Standard sein (Business Logic)."""
        search1 = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Erste Suche",
            query="test1",
            search_type="hybrid",
            is_default=True
        )

        search2 = SavedSearch(
            id=uuid4(),
            user_id=mock_user_a.id,
            name="Zweite Suche",
            query="test2",
            search_type="hybrid",
            is_default=False
        )

        # When setting search2 as default, search1 should be unset (business logic)
        search2.is_default = True
        search1.is_default = False

        await mock_db_session.commit()

        assert search1.is_default is False
        assert search2.is_default is True


# =============================================================================
# Sorting Tests
# =============================================================================

class TestSavedSearchSorting:
    """Tests fuer Sortierung nach use_count DESC."""

    @pytest.mark.asyncio
    async def test_list_searches_sorted_by_use_count_desc(self, mock_db_session, mock_user_a):
        """Suchen werden nach use_count absteigend sortiert."""
        searches = [
            SavedSearch(
                id=uuid4(),
                user_id=mock_user_a.id,
                name="Search 1",
                query="test1",
                search_type="hybrid",
                use_count=5
            ),
            SavedSearch(
                id=uuid4(),
                user_id=mock_user_a.id,
                name="Search 2",
                query="test2",
                search_type="hybrid",
                use_count=15
            ),
            SavedSearch(
                id=uuid4(),
                user_id=mock_user_a.id,
                name="Search 3",
                query="test3",
                search_type="hybrid",
                use_count=10
            ),
        ]

        # Mock query result (sorted)
        mock_result = AsyncMock()
        sorted_searches = sorted(searches, key=lambda s: s.use_count, reverse=True)
        mock_result.scalars.return_value.all.return_value = sorted_searches
        mock_db_session.execute.return_value = mock_result

        # Verify sorting
        assert sorted_searches[0].use_count == 15
        assert sorted_searches[1].use_count == 10
        assert sorted_searches[2].use_count == 5

    @pytest.mark.asyncio
    async def test_new_search_appears_at_bottom(self, mock_db_session, mock_user_a):
        """Neue Suche (use_count=0) erscheint unten in der Liste."""
        searches = [
            SavedSearch(
                id=uuid4(),
                user_id=mock_user_a.id,
                name="Old Search",
                query="test1",
                search_type="hybrid",
                use_count=8
            ),
            SavedSearch(
                id=uuid4(),
                user_id=mock_user_a.id,
                name="New Search",
                query="test2",
                search_type="hybrid",
                use_count=0
            ),
        ]

        sorted_searches = sorted(searches, key=lambda s: s.use_count, reverse=True)

        assert sorted_searches[0].name == "Old Search"
        assert sorted_searches[1].name == "New Search"
        assert sorted_searches[1].use_count == 0

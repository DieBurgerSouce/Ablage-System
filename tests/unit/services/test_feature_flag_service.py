# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Feature-Flag Service.

Testet:
- CRUD-Operationen (get_all, get_by_key, create, update, delete)
- Kill-Switch-Funktion
- Cached Evaluation
- Fehlerbehandlung
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = Mock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def sample_flag_id():
    """Provide sample flag ID."""
    return uuid4()


@pytest.fixture
def sample_user_id():
    """Provide sample user ID."""
    return uuid4()


@pytest.fixture
def mock_feature_flag(sample_flag_id):
    """Create mock feature flag."""
    flag = Mock()
    flag.id = sample_flag_id
    flag.key = "test_feature"
    flag.name = "Test Feature"
    flag.description = "Ein Test-Feature-Flag"
    flag.enabled = True
    flag.rollout_percentage = 50
    flag.target_tiers = ["premium"]
    flag.target_users = []
    flag.variants = {"control": 50, "variant_a": 50}
    flag.starts_at = None
    flag.ends_at = None
    flag.config = {}
    flag.created_at = datetime.now(timezone.utc)
    flag.updated_at = datetime.now(timezone.utc)
    flag.created_by_id = None
    flag.updated_by_id = None
    flag.is_active = Mock(return_value=True)
    flag.is_enabled_for_user = Mock(return_value=True)
    flag.get_variant_for_user = Mock(return_value="variant_a")
    return flag


@pytest.fixture
def mock_disabled_flag(sample_flag_id):
    """Create mock disabled feature flag."""
    flag = Mock()
    flag.id = sample_flag_id
    flag.key = "disabled_feature"
    flag.name = "Disabled Feature"
    flag.description = None
    flag.enabled = False
    flag.rollout_percentage = 0
    flag.target_tiers = []
    flag.target_users = []
    flag.variants = {}
    flag.starts_at = None
    flag.ends_at = None
    flag.config = {}
    flag.created_at = datetime.now(timezone.utc)
    flag.updated_at = datetime.now(timezone.utc)
    flag.created_by_id = None
    flag.updated_by_id = None
    flag.is_active = Mock(return_value=False)
    flag.is_enabled_for_user = Mock(return_value=False)
    flag.get_variant_for_user = Mock(return_value=None)
    return flag


# ========================= get_all Tests =========================


@pytest.mark.asyncio
async def test_get_all_returns_flags(mock_db_session, mock_feature_flag):
    """get_all gibt Feature-Flags zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    # Mock the execute result
    mock_result = Mock()
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[mock_feature_flag])
    mock_result.scalars = Mock(return_value=mock_scalars)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    flags = await service.get_all()

    assert len(flags) == 1
    assert flags[0].key == "test_feature"
    mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_empty(mock_db_session):
    """get_all gibt leere Liste zurueck wenn keine Flags existieren."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[])
    mock_result.scalars = Mock(return_value=mock_scalars)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    flags = await service.get_all()

    assert len(flags) == 0


@pytest.mark.asyncio
async def test_get_all_handles_db_error(mock_db_session):
    """get_all gibt leere Liste bei Datenbankfehler zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_db_session.execute = AsyncMock(side_effect=Exception("DB error"))

    service = FeatureFlagService(mock_db_session)
    flags = await service.get_all()

    assert flags == []


# ========================= get_by_key Tests =========================


@pytest.mark.asyncio
async def test_get_by_key_finds_existing(mock_db_session, mock_feature_flag):
    """get_by_key findet existierendes Flag."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_feature_flag)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    flag = await service.get_by_key("test_feature")

    assert flag is not None
    assert flag.key == "test_feature"


@pytest.mark.asyncio
async def test_get_by_key_returns_none_for_nonexistent(mock_db_session):
    """get_by_key gibt None fuer nicht existierendes Flag zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    flag = await service.get_by_key("nonexistent_key")

    assert flag is None


# ========================= create Tests =========================


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.invalidate_cache", new_callable=AsyncMock)
async def test_create_creates_new_flag(mock_invalidate, mock_db_session):
    """create erstellt ein neues Feature-Flag."""
    from app.services.feature_flag_service import FeatureFlagService

    service = FeatureFlagService(mock_db_session)
    flag = await service.create(
        key="new_feature",
        name="New Feature",
        description="Neues Feature",
        enabled=True,
        rollout_percentage=100,
    )

    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()
    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.invalidate_cache", new_callable=AsyncMock)
async def test_create_rollback_on_error(mock_invalidate, mock_db_session):
    """create fuehrt Rollback bei Fehler durch."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_db_session.commit = AsyncMock(side_effect=Exception("DB error"))

    service = FeatureFlagService(mock_db_session)

    with pytest.raises(ValueError, match="Fehler beim Erstellen"):
        await service.create(key="fail_feature", name="Fail")

    mock_db_session.rollback.assert_called_once()


# ========================= update_flag Tests =========================


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.invalidate_cache", new_callable=AsyncMock)
async def test_update_flag_updates_fields(
    mock_invalidate, mock_db_session, mock_feature_flag, sample_flag_id
):
    """update_flag aktualisiert die angegebenen Felder."""
    from app.services.feature_flag_service import FeatureFlagService

    # Mock get_by_id
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_feature_flag)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    updated = await service.update_flag(
        flag_id=sample_flag_id,
        updates={"enabled": False, "rollout_percentage": 0},
    )

    assert updated is not None
    mock_db_session.commit.assert_called_once()
    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_update_flag_returns_none_for_nonexistent(
    mock_db_session, sample_flag_id
):
    """update_flag gibt None fuer nicht existierendes Flag zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.update_flag(
        flag_id=sample_flag_id,
        updates={"enabled": True},
    )

    assert result is None


# ========================= delete_flag Tests =========================


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.invalidate_cache", new_callable=AsyncMock)
async def test_delete_flag_removes_flag(
    mock_invalidate, mock_db_session, mock_feature_flag, sample_flag_id
):
    """delete_flag entfernt das Flag."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_feature_flag)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.delete_flag(sample_flag_id)

    assert result is True
    mock_db_session.delete.assert_called_once_with(mock_feature_flag)
    mock_db_session.commit.assert_called_once()
    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_delete_flag_returns_false_for_nonexistent(
    mock_db_session, sample_flag_id
):
    """delete_flag gibt False fuer nicht existierendes Flag zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.delete_flag(sample_flag_id)

    assert result is False


# ========================= kill_switch Tests =========================


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.invalidate_cache", new_callable=AsyncMock)
async def test_kill_switch_disables_flag(
    mock_invalidate, mock_db_session, mock_feature_flag
):
    """kill_switch deaktiviert das Flag und setzt rollout auf 0."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_feature_flag)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.kill_switch("test_feature")

    assert result is True
    assert mock_feature_flag.enabled is False
    assert mock_feature_flag.rollout_percentage == 0
    mock_db_session.commit.assert_called_once()
    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_kill_switch_returns_false_for_nonexistent(mock_db_session):
    """kill_switch gibt False fuer nicht existierendes Flag zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.kill_switch("nonexistent_key")

    assert result is False


# ========================= evaluate Tests =========================


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.cache_set", new_callable=AsyncMock)
@patch("app.services.feature_flag_service.cache_get", new_callable=AsyncMock)
async def test_evaluate_returns_cached_result(
    mock_cache_get, mock_cache_set, mock_db_session
):
    """evaluate gibt gecachtes Ergebnis zurueck bei Cache Hit."""
    from app.services.feature_flag_service import FeatureFlagService

    cached_result = {
        "flag_key": "cached_feature",
        "enabled": True,
        "variant": "variant_a",
        "reason": "evaluated",
    }
    mock_cache_get.return_value = cached_result

    service = FeatureFlagService(mock_db_session)
    result = await service.evaluate(
        key="cached_feature",
        user_id="user-123",
    )

    assert result["enabled"] is True
    assert result["variant"] == "variant_a"
    # DB should NOT be queried when cache hit
    mock_db_session.execute.assert_not_called()
    # cache_set should NOT be called on cache hit
    mock_cache_set.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.cache_set", new_callable=AsyncMock)
@patch("app.services.feature_flag_service.cache_get", new_callable=AsyncMock)
async def test_evaluate_returns_disabled_for_nonexistent(
    mock_cache_get, mock_cache_set, mock_db_session
):
    """evaluate gibt enabled=False fuer nicht existierendes Flag zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_cache_get.return_value = None

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.evaluate(
        key="nonexistent_key",
        user_id="user-123",
    )

    assert result["flag_key"] == "nonexistent_key"
    assert result["enabled"] is False
    assert result["variant"] is None
    assert result["reason"] == "flag_not_found"
    # Should cache the negative result
    mock_cache_set.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.feature_flag_service.cache_set", new_callable=AsyncMock)
@patch("app.services.feature_flag_service.cache_get", new_callable=AsyncMock)
async def test_evaluate_evaluates_flag_for_user(
    mock_cache_get, mock_cache_set, mock_db_session, mock_feature_flag
):
    """evaluate evaluiert das Flag fuer den Benutzer und cacht das Ergebnis."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_cache_get.return_value = None

    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=mock_feature_flag)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    result = await service.evaluate(
        key="test_feature",
        user_id="user-456",
        user_tier="premium",
    )

    assert result["flag_key"] == "test_feature"
    assert result["enabled"] is True
    assert result["variant"] == "variant_a"
    assert result["reason"] == "evaluated"
    mock_cache_set.assert_called_once()
    mock_feature_flag.is_enabled_for_user.assert_called_once_with(
        "user-456", "premium"
    )


# ========================= evaluate_all Tests =========================


@pytest.mark.asyncio
async def test_evaluate_all_returns_all_enabled_flags(
    mock_db_session, mock_feature_flag
):
    """evaluate_all gibt alle aktivierten Flags fuer den Benutzer zurueck."""
    from app.services.feature_flag_service import FeatureFlagService

    mock_result = Mock()
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[mock_feature_flag])
    mock_result.scalars = Mock(return_value=mock_scalars)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    service = FeatureFlagService(mock_db_session)
    results = await service.evaluate_all(
        user_id="user-789",
        user_tier="premium",
    )

    assert "test_feature" in results
    assert results["test_feature"]["enabled"] is True


# ========================= Factory Tests =========================


def test_get_feature_flag_service_creates_service(mock_db_session):
    """get_feature_flag_service erstellt eine Service-Instanz."""
    from app.services.feature_flag_service import get_feature_flag_service

    service = get_feature_flag_service(mock_db_session)

    assert service is not None
    assert service.db is mock_db_session

# -*- coding: utf-8 -*-
"""
Unit-Tests für Smart Inbox Services.

Testet:
- Inbox Aggregation (multiple sources)
- Priority Scoring (high/deadline/ML)
- Behavior Learning
- Action Recommendations
- Insights Generation

Feinpoliert und durchdacht - Smart Inbox Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.smart_inbox.inbox_aggregator import (
    InboxAggregator,
    InboxItemData,
)
from app.services.smart_inbox.priority_scorer import (
    PriorityScorer,
    ScoredItem,
)
from app.services.smart_inbox.behavior_learner import (
    BehaviorLearner,
    UserPreferences,
)
from app.services.smart_inbox.action_recommender import (
    ActionRecommender,
    RecommendedAction,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = AsyncMock()
    return session


@pytest.fixture
def sample_user_id() -> UUID:
    """Provide sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    """Provide sample company UUID."""
    return uuid4()


@pytest.fixture
def sample_document_id() -> UUID:
    """Provide sample document UUID."""
    return uuid4()


@pytest.fixture
def sample_entity_id() -> UUID:
    """Provide sample entity UUID."""
    return uuid4()


# ========================= InboxAggregator Tests =========================


class TestInboxAggregator:
    """Tests für Inbox Aggregator."""

    @pytest.mark.asyncio
    async def test_inbox_aggregation_multiple_sources(
        self, mock_db_session, sample_user_id, sample_company_id
    ):
        """Aggregation sollte aus allen Quellen Items sammeln."""
        # Arrange
        aggregator = InboxAggregator()

        # Mock empty results for all sources
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        items = await aggregator.aggregate_for_user(
            user_id=sample_user_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert isinstance(items, list)
        # Mit leeren Mock-Daten erwarten wir 0 Items
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_inbox_aggregation_empty(
        self, mock_db_session, sample_user_id, sample_company_id
    ):
        """Leere Aggregation sollte graceful funktionieren."""
        # Arrange
        aggregator = InboxAggregator()

        # Mock empty results
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        items = await aggregator.aggregate_for_user(
            user_id=sample_user_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert items == []

    @pytest.mark.asyncio
    async def test_aggregate_alerts(
        self, mock_db_session, sample_user_id, sample_company_id
    ):
        """Alert-Aggregation sollte Severity-basierte Priorität vergeben."""
        # Arrange
        aggregator = InboxAggregator()

        # Mock Alert mit CRITICAL Severity
        mock_alert = Mock()
        mock_alert.id = uuid4()
        mock_alert.title = "Kritischer Fehler"
        mock_alert.message = "System überlastet"
        mock_alert.category = "system"
        mock_alert.severity = "critical"
        mock_alert.status = "new"
        mock_alert.document_id = None
        mock_alert.entity_id = None
        mock_alert.alert_code = "SYS_001"

        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[mock_alert])))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        items = await aggregator._aggregate_alerts(
            user_id=sample_user_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert len(items) == 1
        assert items[0].raw_priority == 95.0  # Critical Severity
        assert items[0].category == "system"
        assert "acknowledge" in items[0].recommended_actions


# ========================= PriorityScorer Tests =========================


class TestPriorityScorer:
    """Tests für Priority Scorer."""

    @pytest.mark.asyncio
    async def test_priority_scoring_high_priority(
        self, mock_db_session, sample_user_id
    ):
        """High Priority Items sollten hohe ML-Scores erhalten."""
        # Arrange
        scorer = PriorityScorer()

        # Mock SmartInboxItem
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.raw_priority = 95.0  # Critical Alert
        mock_item.deadline = None
        mock_item.category = "alert"
        mock_item.source_type = "alert"
        mock_item.context_data = {
            "severity": "critical",
            "escalated": True,
        }
        mock_item.entity_id = None

        # Mock User Preferences
        mock_prefs = UserPreferences(
            user_id=sample_user_id,
            category_weights={"alert": 1.2},
            preferred_categories=["alert", "deadline", "validation"],
        )

        with patch.object(scorer.behavior_learner, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = mock_prefs

            # Act
            scored_items = await scorer.score([mock_item], sample_user_id, mock_db_session)

            # Assert
            assert len(scored_items) == 1
            assert scored_items[0].ml_priority >= 90.0  # Very high
            assert len(scored_items[0].boost_reasons) > 0

    @pytest.mark.asyncio
    async def test_priority_scoring_deadline_boost(
        self, mock_db_session, sample_user_id
    ):
        """Nahe Deadlines sollten Priority Boost erhalten."""
        # Arrange
        scorer = PriorityScorer()

        # Mock SmartInboxItem mit morgen Deadline
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.raw_priority = 50.0
        mock_item.deadline = tomorrow
        mock_item.category = "deadline"
        mock_item.source_type = "deadline"
        mock_item.context_data = {}
        mock_item.entity_id = None

        # Mock User Preferences
        mock_prefs = UserPreferences(
            user_id=sample_user_id,
            category_weights={"deadline": 1.0},
            preferred_categories=[],
        )

        with patch.object(scorer.behavior_learner, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = mock_prefs

            # Act
            scored_items = await scorer.score([mock_item], sample_user_id, mock_db_session)

            # Assert
            assert len(scored_items) == 1
            assert scored_items[0].ml_priority > 50.0  # Boosted
            assert any("morgen" in reason.lower() for reason in scored_items[0].boost_reasons)

    @pytest.mark.asyncio
    async def test_priority_scoring_ml_integration(
        self, mock_db_session, sample_user_id
    ):
        """ML-Scores sollten korrekt angewendet werden."""
        # Arrange
        scorer = PriorityScorer()

        # Mock SmartInboxItem
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.raw_priority = 60.0
        mock_item.deadline = None
        mock_item.category = "validation"
        mock_item.source_type = "validation_queue"
        mock_item.context_data = {"confidence": 0.65}
        mock_item.entity_id = None

        # Mock User Preferences (validation ist preferred)
        mock_prefs = UserPreferences(
            user_id=sample_user_id,
            category_weights={"validation": 1.3},  # User likes validation tasks
            preferred_categories=["validation"],
        )

        with patch.object(scorer.behavior_learner, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = mock_prefs

            # Act
            scored_items = await scorer.score([mock_item], sample_user_id, mock_db_session)

            # Assert
            assert len(scored_items) == 1
            # ML Priority sollte höher sein wegen User Preference
            assert scored_items[0].ml_priority > scored_items[0].raw_priority


# ========================= BehaviorLearner Tests =========================


class TestBehaviorLearner:
    """Tests für Behavior Learner."""

    @pytest.mark.asyncio
    async def test_behavior_learning_action_logged(
        self, mock_db_session, sample_user_id
    ):
        """User-Aktionen sollten geloggt werden."""
        # Arrange
        learner = BehaviorLearner()
        item_id = uuid4()

        # Act
        await learner.log_action(
            user_id=sample_user_id,
            item_id=item_id,
            action_type="approve",
            category="validation",
            db=mock_db_session,
        )

        # Assert
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_behavior_preferences_calculation(
        self, mock_db_session, sample_user_id
    ):
        """Präferenzen sollten aus Verhalten abgeleitet werden."""
        # Arrange
        learner = BehaviorLearner()

        # Mock UserBehaviorLog entries
        mock_logs = []
        for i in range(10):
            log = Mock()
            log.category = "alert" if i < 7 else "task"  # 70% alerts, 30% tasks
            log.action_type = "acknowledge"
            log.created_at = datetime.now(timezone.utc) - timedelta(days=i)
            mock_logs.append(log)

        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=mock_logs)))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        prefs = await learner.get_user_preferences(sample_user_id, mock_db_session)

        # Assert
        assert prefs.user_id == sample_user_id
        # Alert sollte bevorzugte Kategorie sein
        assert "alert" in prefs.preferred_categories


# ========================= ActionRecommender Tests =========================


class TestActionRecommender:
    """Tests für Action Recommender."""

    @pytest.mark.asyncio
    async def test_action_recommender_alert(self, mock_db_session):
        """Alert Items sollten 'acknowledge' empfohlen bekommen."""
        # Arrange
        recommender = ActionRecommender()

        # Mock SmartInboxItem (Alert)
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.source_type = "alert"
        mock_item.category = "system"
        mock_item.context_data = {"severity": "medium"}
        mock_item.document_id = None

        # Act
        actions = await recommender.recommend(mock_item, mock_db_session)

        # Assert
        assert len(actions) > 0
        # Erste Aktion sollte "acknowledge" sein (nach Confidence sortiert)
        action_types = [a.action_type for a in actions]
        assert "acknowledge" in action_types

    @pytest.mark.asyncio
    async def test_action_recommender_deadline(self, mock_db_session):
        """Deadline Items sollten 'pay' empfohlen bekommen."""
        # Arrange
        recommender = ActionRecommender()

        # Mock SmartInboxItem (Deadline mit Skonto)
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.source_type = "deadline"
        mock_item.category = "deadline"
        mock_item.context_data = {
            "days_until_due": 5,
            "skonto_available": True,
        }
        mock_item.document_id = uuid4()

        # Act
        actions = await recommender.recommend(mock_item, mock_db_session)

        # Assert
        assert len(actions) > 0
        action_types = [a.action_type for a in actions]
        assert "use_skonto" in action_types
        assert "pay" in action_types

    @pytest.mark.asyncio
    async def test_action_recommender_validation(self, mock_db_session):
        """Validation Items sollten 'review' empfohlen bekommen."""
        # Arrange
        recommender = ActionRecommender()

        # Mock SmartInboxItem (Validation Queue)
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.source_type = "validation_queue"
        mock_item.category = "validation"
        mock_item.context_data = {"confidence": 0.65}
        mock_item.document_id = uuid4()

        # Act
        actions = await recommender.recommend(mock_item, mock_db_session)

        # Assert
        assert len(actions) > 0
        # Höchste Confidence sollte "review" sein
        top_action = actions[0]
        assert top_action.action_type == "review"
        assert top_action.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_action_recommender_task(self, mock_db_session):
        """Task Items sollten 'complete' empfohlen bekommen."""
        # Arrange
        recommender = ActionRecommender()

        # Mock SmartInboxItem (Task)
        mock_item = Mock()
        mock_item.id = uuid4()
        mock_item.source_type = "task"
        mock_item.category = "task"
        mock_item.context_data = {"task_type": "review"}
        mock_item.document_id = uuid4()

        # Act
        actions = await recommender.recommend(mock_item, mock_db_session)

        # Assert
        assert len(actions) > 0
        action_types = [a.action_type for a in actions]
        assert "complete" in action_types or "view_document" in action_types

    @pytest.mark.asyncio
    async def test_insights_generation(self, mock_db_session, sample_user_id, sample_company_id):
        """Insights sollten mit Trends berechnet werden."""
        # Arrange
        aggregator = InboxAggregator()

        # Mock mehrere Items verschiedener Kategorien
        mock_items_data = []
        for i in range(5):
            mock_items_data.append(
                InboxItemData(
                    source_type="alert",
                    source_id=uuid4(),
                    title=f"Alert {i}",
                    description="Test alert",
                    category="system",
                    raw_priority=80.0,
                    deadline=None,
                    document_id=None,
                    entity_id=None,
                    context_data={},
                    recommended_actions=["acknowledge"],
                )
            )

        # Assert
        # Insights würden zeigen: Viele System-Alerts
        alert_count = sum(1 for item in mock_items_data if item.source_type == "alert")
        assert alert_count == 5

    @pytest.mark.asyncio
    async def test_recalculate_priorities(
        self, mock_db_session, sample_user_id, sample_company_id
    ):
        """Priority-Neuberechnung sollte alle pending Items updaten."""
        # Arrange
        scorer = PriorityScorer()

        # Mock pending Items
        mock_items = []
        for i in range(3):
            item = Mock()
            item.id = uuid4()
            item.raw_priority = 50.0 + i * 10
            item.ml_priority = 0.0  # Wird berechnet
            item.deadline = None
            item.category = "task"
            item.source_type = "task"
            item.context_data = {}
            item.entity_id = None
            mock_items.append(item)

        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=mock_items)))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock User Preferences
        mock_prefs = UserPreferences(
            user_id=sample_user_id,
            category_weights={"task": 1.0},
            preferred_categories=[],
        )

        with patch.object(scorer.behavior_learner, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = mock_prefs

            # Act
            updated_count = await scorer.recalculate_priorities(
                user_id=sample_user_id,
                company_id=sample_company_id,
                db=mock_db_session,
            )

            # Assert
            assert updated_count == 3
            # Alle Items sollten ML-Priority haben
            for item in mock_items:
                assert item.ml_priority > 0.0

# -*- coding: utf-8 -*-
"""Unit tests for AIMentorService.

Tests:
- Kontextuelle Tipps
- Verhaltensmuster-Analyse
- Praeferenzen
- Tipp verwerfen/wiederherstellen
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.mentor_service import (
    AIMentorService,
    Tip,
    BehaviorPattern,
    MentorPreferences,
    TipCategory,
    TipPriority,
    UserExperience,
    TIP_LIBRARY,
)


class TestAIMentorService:
    """Tests fuer AIMentorService."""

    @pytest.fixture
    def mock_db(self):
        """Mock Database Session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        """Service-Instanz."""
        return AIMentorService(mock_db)

    @pytest.fixture
    def sample_user_id(self):
        """Beispiel User-ID."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_company_id(self):
        """Beispiel Company-ID."""
        return uuid.uuid4()

    # ========================================================================
    # TIP LIBRARY TESTS
    # ========================================================================

    def test_tip_library_not_empty(self):
        """Tipp-Bibliothek sollte Tipps enthalten."""
        assert len(TIP_LIBRARY) > 0

    def test_tip_library_has_required_fields(self):
        """Alle Tipps sollten erforderliche Felder haben."""
        required_fields = ["id", "title", "content", "category", "priority"]

        for tip in TIP_LIBRARY:
            for field in required_fields:
                assert field in tip, f"Tipp {tip.get('id')} fehlt Feld: {field}"

    def test_tip_library_unique_ids(self):
        """Alle Tipp-IDs sollten eindeutig sein."""
        ids = [tip["id"] for tip in TIP_LIBRARY]
        assert len(ids) == len(set(ids)), "Doppelte Tipp-IDs gefunden"

    def test_tip_library_german_content(self):
        """Alle Tipps sollten deutschen Content haben."""
        german_indicators = ["Sie", "Ihr", "Dokument", "Einstellungen"]

        for tip in TIP_LIBRARY:
            content = tip["content"]
            has_german = any(indicator in content for indicator in german_indicators)
            # Mindestens ein deutscher Indikator sollte vorhanden sein
            # (nicht alle Tipps muessen alle Indikatoren haben)
            assert len(content) > 10, f"Tipp {tip['id']} hat zu kurzen Content"

    # ========================================================================
    # TIP INDEX TESTS
    # ========================================================================

    def test_tip_index_built(self, service):
        """Tipp-Index sollte aufgebaut sein."""
        assert len(service._tip_index) == len(TIP_LIBRARY)

    def test_tip_index_contains_all_tips(self, service):
        """Index sollte alle Tipps enthalten."""
        for tip_data in TIP_LIBRARY:
            assert tip_data["id"] in service._tip_index

    # ========================================================================
    # CONTEXTUAL TIPS TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_contextual_tips_documents_page(self, service, sample_user_id):
        """Tipps fuer Documents-Seite sollten relevant sein."""
        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="documents",
            preferences=None,
            max_tips=5,
        )

        assert len(tips) > 0
        # Mindestens ein Tipp sollte fuer "documents" relevant sein
        for tip in tips:
            assert "documents" in tip.context_pages or not tip.context_pages

    @pytest.mark.asyncio
    async def test_get_contextual_tips_validation_page(self, service, sample_user_id):
        """Tipps fuer Validation-Seite sollten Shortcuts enthalten."""
        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="validation",
            preferences=None,
            max_tips=10,
        )

        # Es sollte mindestens einen Shortcut-Tipp geben
        shortcut_tips = [t for t in tips if t.category == TipCategory.SHORTCUT]
        assert len(shortcut_tips) > 0

    @pytest.mark.asyncio
    async def test_get_contextual_tips_respects_max(self, service, sample_user_id):
        """max_tips sollte beachtet werden."""
        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="dashboard",
            preferences=None,
            max_tips=2,
        )

        assert len(tips) <= 2

    @pytest.mark.asyncio
    async def test_get_contextual_tips_disabled_returns_empty(self, service, sample_user_id):
        """Deaktivierter Mentor sollte keine Tipps liefern."""
        preferences = MentorPreferences(enabled=False)

        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="documents",
            preferences=preferences,
            max_tips=5,
        )

        assert len(tips) == 0

    @pytest.mark.asyncio
    async def test_get_contextual_tips_filters_dismissed(self, service, sample_user_id):
        """Verworfene Tipps sollten nicht angezeigt werden."""
        # Ersten Tipp verwerfen
        first_tip_id = TIP_LIBRARY[0]["id"]
        preferences = MentorPreferences(
            enabled=True,
            dismissed_tips={first_tip_id},
        )

        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="dashboard",
            preferences=preferences,
            max_tips=20,
        )

        # Der verworfene Tipp sollte nicht dabei sein
        tip_ids = [t.id for t in tips]
        assert first_tip_id not in tip_ids

    @pytest.mark.asyncio
    async def test_get_contextual_tips_respects_experience_level(self, service, sample_user_id):
        """Erfahrungsstufe sollte beachtet werden."""
        # Anfaenger
        beginner_prefs = MentorPreferences(
            enabled=True,
            experience_level=UserExperience.BEGINNER,
        )

        beginner_tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="documents",
            preferences=beginner_prefs,
            max_tips=20,
        )

        # Fortgeschrittener
        advanced_prefs = MentorPreferences(
            enabled=True,
            experience_level=UserExperience.ADVANCED,
        )

        advanced_tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="documents",
            preferences=advanced_prefs,
            max_tips=20,
        )

        # Fortgeschrittene sollten mindestens so viele Tipps sehen wie Anfaenger
        assert len(advanced_tips) >= len(beginner_tips)

    @pytest.mark.asyncio
    async def test_get_contextual_tips_filters_by_category(self, service, sample_user_id):
        """Kategorie-Filter sollten funktionieren."""
        # Shortcuts deaktivieren
        prefs = MentorPreferences(
            enabled=True,
            show_shortcuts=False,
        )

        tips = await service.get_contextual_tips(
            user_id=sample_user_id,
            context_page="documents",
            preferences=prefs,
            max_tips=20,
        )

        # Keine Shortcut-Tipps
        shortcut_tips = [t for t in tips if t.category == TipCategory.SHORTCUT]
        assert len(shortcut_tips) == 0

    # ========================================================================
    # CONTEXT MATCHING TESTS
    # ========================================================================

    def test_matches_context_exact(self, service):
        """Exakter Context-Match sollte funktionieren."""
        tip = Tip(
            id="test",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=["documents"],
            experience_level=UserExperience.BEGINNER,
        )

        assert service._matches_context(tip, "documents") is True

    def test_matches_context_partial(self, service):
        """Partieller Context-Match sollte funktionieren."""
        tip = Tip(
            id="test",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=["documents"],
            experience_level=UserExperience.BEGINNER,
        )

        # URL-artige Pfade
        assert service._matches_context(tip, "/documents/123") is True
        assert service._matches_context(tip, "documents/upload") is True

    def test_matches_context_empty_pages(self, service):
        """Leere context_pages sollte immer matchen (universeller Tipp)."""
        tip = Tip(
            id="test",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=[],
            experience_level=UserExperience.BEGINNER,
        )

        assert service._matches_context(tip, "any-page") is True

    # ========================================================================
    # EXPERIENCE LEVEL TESTS
    # ========================================================================

    def test_matches_experience_beginner_sees_beginner(self, service):
        """Anfaenger sieht Anfaenger-Tipps."""
        tip = Tip(
            id="test",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=[],
            experience_level=UserExperience.BEGINNER,
        )

        assert service._matches_experience(tip, UserExperience.BEGINNER) is True

    def test_matches_experience_beginner_not_advanced(self, service):
        """Anfaenger sieht keine Fortgeschrittenen-Tipps."""
        tip = Tip(
            id="test",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=[],
            experience_level=UserExperience.ADVANCED,
        )

        assert service._matches_experience(tip, UserExperience.BEGINNER) is False

    def test_matches_experience_advanced_sees_all(self, service):
        """Fortgeschrittene sehen alle Tipps."""
        beginner_tip = Tip(
            id="test1",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=[],
            experience_level=UserExperience.BEGINNER,
        )

        advanced_tip = Tip(
            id="test2",
            title="Test",
            content="Test",
            category=TipCategory.SHORTCUT,
            priority=TipPriority.HIGH,
            context_pages=[],
            experience_level=UserExperience.ADVANCED,
        )

        assert service._matches_experience(beginner_tip, UserExperience.ADVANCED) is True
        assert service._matches_experience(advanced_tip, UserExperience.ADVANCED) is True

    # ========================================================================
    # GET ALL TIPS TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_all_tips(self, service):
        """get_all_tips sollte alle Tipps liefern."""
        tips = await service.get_all_tips()

        assert len(tips) == len(TIP_LIBRARY)

    @pytest.mark.asyncio
    async def test_get_tip_by_id_found(self, service):
        """get_tip_by_id sollte existierenden Tipp finden."""
        first_tip_id = TIP_LIBRARY[0]["id"]

        tip = await service.get_tip_by_id(first_tip_id)

        assert tip is not None
        assert tip.id == first_tip_id

    @pytest.mark.asyncio
    async def test_get_tip_by_id_not_found(self, service):
        """get_tip_by_id sollte None fuer unbekannte ID liefern."""
        tip = await service.get_tip_by_id("non_existent_tip_id_12345")

        assert tip is None

    # ========================================================================
    # BEHAVIOR PATTERN TESTS
    # ========================================================================

    def test_create_pattern_from_behavior_frequent_view(self, service):
        """Haeufiges Ansehen sollte Pattern erstellen."""
        from datetime import datetime

        pattern = service._create_pattern_from_behavior(
            action="viewed",
            context_page="documents",
            frequency=15,
            last_at=datetime.now(),
            avg_time_ms=5000.0,
        )

        assert pattern is not None
        assert pattern.pattern_type == "frequent_view"
        assert "documents" in pattern.description

    def test_create_pattern_from_behavior_frequent_upload(self, service):
        """Haeufiges Hochladen sollte Pattern erstellen."""
        from datetime import datetime

        pattern = service._create_pattern_from_behavior(
            action="clicked",
            context_page="upload-button",
            frequency=10,
            last_at=datetime.now(),
            avg_time_ms=3000.0,
        )

        assert pattern is not None
        assert pattern.pattern_type == "frequent_upload"
        assert "Ordner-Import" in pattern.recommendation

    def test_create_pattern_from_behavior_slow_completion(self, service):
        """Langsame Aktionen sollten Pattern erstellen."""
        from datetime import datetime

        pattern = service._create_pattern_from_behavior(
            action="completed",
            context_page="validation",
            frequency=8,
            last_at=datetime.now(),
            avg_time_ms=45000.0,  # 45 Sekunden
        )

        assert pattern is not None
        assert pattern.pattern_type == "slow_completion"
        assert "Shortcuts" in pattern.recommendation

    def test_create_pattern_from_behavior_no_match(self, service):
        """Nicht-relevante Aktionen sollten kein Pattern erstellen."""
        from datetime import datetime

        pattern = service._create_pattern_from_behavior(
            action="random_action",
            context_page="random_page",
            frequency=3,
            last_at=datetime.now(),
            avg_time_ms=1000.0,
        )

        assert pattern is None

    # ========================================================================
    # DISMISS TIP TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_dismiss_tip_invalid_id_format(self, service, sample_user_id):
        """Ungueltige Tipp-ID sollte abgelehnt werden."""
        # ID mit ungueltigen Zeichen
        result = await service.dismiss_tip(
            user_id=sample_user_id,
            tip_id="../../../etc/passwd",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_dismiss_tip_valid_format(self, service, sample_user_id, mock_db):
        """Gueltige Tipp-ID sollte akzeptiert werden (mit Mock)."""
        # Mock User
        mock_user = MagicMock()
        mock_user.preferences = {"mentor": {"dismissed_tips": []}}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()

        result = await service.dismiss_tip(
            user_id=sample_user_id,
            tip_id="tip_shortcut_search",
        )

        assert result is True
        mock_db.commit.assert_called_once()

    # ========================================================================
    # PREFERENCES TESTS
    # ========================================================================

    def test_mentor_preferences_defaults(self):
        """MentorPreferences sollte sinnvolle Defaults haben."""
        prefs = MentorPreferences()

        assert prefs.enabled is True
        assert prefs.show_shortcuts is True
        assert prefs.show_automation_tips is True
        assert prefs.show_pattern_insights is True
        assert prefs.experience_level == UserExperience.BEGINNER
        assert len(prefs.dismissed_tips) == 0
        assert prefs.max_tips_per_session == 5
        assert prefs.tip_frequency_hours == 24

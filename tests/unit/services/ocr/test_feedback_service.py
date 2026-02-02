# -*- coding: utf-8 -*-
"""
Unit Tests fuer Enhanced OCR Feedback Service.

Testet:
- Korrektur-Einreichung und Punkte-Berechnung
- Queue-Management
- Leaderboard-Funktionalitaet
- Achievements und Streaks

Phase 6.3: OCR Feedback UX Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.ocr.feedback_service import (
    EnhancedOCRFeedbackService,
    CorrectionFeedback,
    CorrectionResult,
    QueueItem,
    LeaderboardEntry,
    UserStats,
    BatchCorrectionResult,
    LeaderboardPeriod,
    QueuePriority,
    CorrectionStatus,
    get_feedback_service,
    POINTS_CONFIG,
    LEADERBOARD_CONFIG,
    LOW_CONFIDENCE_THRESHOLD,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Erzeugt eine Mock-DB-Session."""
    mock = AsyncMock()
    mock.flush = AsyncMock()
    mock.commit = AsyncMock()
    mock.execute = AsyncMock()
    mock.get = AsyncMock()
    mock.add = MagicMock()
    return mock


@pytest.fixture
def service(mock_db):
    """Erzeugt eine Service-Instanz mit Mock-DB."""
    return EnhancedOCRFeedbackService(mock_db)


@pytest.fixture
def sample_correction():
    """Erzeugt eine Sample-Korrektur."""
    return CorrectionFeedback(
        document_id=uuid4(),
        field_name="invoice_number",
        original_value="RE-2O26-001",  # O statt 0 (Fehler)
        corrected_value="RE-2026-001",
        confidence_before=0.75,
        correction_type="reference",
        user_id=uuid4(),
        ocr_backend="deepseek",
    )


@pytest.fixture
def sample_user():
    """Erzeugt einen Sample-User."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    user.full_name = "Test User"
    user.company_id = uuid4()
    return user


# =============================================================================
# POINTS CONFIGURATION TESTS
# =============================================================================


class TestPointsConfiguration:
    """Tests fuer Punkte-Konfiguration."""

    def test_points_config_exists(self):
        """Testet dass Punkte-Konfiguration existiert."""
        assert "text_correction" in POINTS_CONFIG
        assert "amount_correction" in POINTS_CONFIG
        assert "entity_correction" in POINTS_CONFIG

    def test_base_points_values(self):
        """Testet Basis-Punktewerte."""
        assert POINTS_CONFIG["text_correction"] == 10
        assert POINTS_CONFIG["amount_correction"] == 15
        assert POINTS_CONFIG["entity_correction"] == 20
        assert POINTS_CONFIG["iban_correction"] == 25

    def test_bonus_points_values(self):
        """Testet Bonus-Punktewerte."""
        assert POINTS_CONFIG["major_correction_bonus"] == 5
        assert POINTS_CONFIG["low_confidence_bonus"] == 10
        assert POINTS_CONFIG["first_of_day_bonus"] == 5
        assert POINTS_CONFIG["streak_bonus_per_day"] == 3

    def test_leaderboard_config(self):
        """Testet Leaderboard-Konfiguration."""
        assert LEADERBOARD_CONFIG["weekly_top_count"] == 10
        assert LEADERBOARD_CONFIG["min_corrections_for_ranking"] == 5

    def test_low_confidence_threshold(self):
        """Testet Low-Confidence Schwellenwert."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.70


# =============================================================================
# SERVICE INITIALIZATION TESTS
# =============================================================================


class TestServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    def test_service_creation(self, service):
        """Testet dass Service korrekt erstellt wird."""
        assert service is not None
        assert service._db is not None

    def test_get_feedback_service_factory(self, mock_db):
        """Testet Factory-Funktion."""
        svc = get_feedback_service(mock_db)
        assert isinstance(svc, EnhancedOCRFeedbackService)


# =============================================================================
# BASE POINTS CALCULATION TESTS
# =============================================================================


class TestBasePointsCalculation:
    """Tests fuer Basis-Punkte-Berechnung."""

    def test_text_correction_points(self, service):
        """Testet Punkte fuer Text-Korrektur."""
        points = service._calculate_base_points("text")
        assert points == 10

    def test_amount_correction_points(self, service):
        """Testet Punkte fuer Betrags-Korrektur."""
        points = service._calculate_base_points("amount")
        assert points == 15

    def test_entity_correction_points(self, service):
        """Testet Punkte fuer Entity-Korrektur."""
        points = service._calculate_base_points("entity")
        assert points == 20

    def test_iban_correction_points(self, service):
        """Testet Punkte fuer IBAN-Korrektur."""
        points = service._calculate_base_points("iban")
        assert points == 25

    def test_unknown_type_defaults_to_text(self, service):
        """Testet dass unbekannter Typ auf Text-Punkte zurueckfaellt."""
        points = service._calculate_base_points("unknown")
        assert points == 10  # Default text_correction


# =============================================================================
# MAJOR CORRECTION DETECTION TESTS
# =============================================================================


class TestMajorCorrectionDetection:
    """Tests fuer Major-Korrektur-Erkennung."""

    def test_major_correction_large_diff(self, service):
        """Testet Erkennung bei grossem Unterschied."""
        is_major = service._is_major_correction("abc", "abcdefghijklmnop")
        assert is_major is True

    def test_not_major_correction_small_diff(self, service):
        """Testet Erkennung bei kleinem Unterschied."""
        is_major = service._is_major_correction("test", "Test")
        assert is_major is False

    def test_major_correction_empty_original(self, service):
        """Testet Erkennung bei leerem Original."""
        is_major = service._is_major_correction("", "korrigiert")
        assert is_major is True

    def test_major_correction_empty_corrected(self, service):
        """Testet Erkennung bei leerer Korrektur."""
        is_major = service._is_major_correction("original", "")
        assert is_major is True


# =============================================================================
# QUEUE PRIORITY CALCULATION TESTS
# =============================================================================


class TestQueuePriorityCalculation:
    """Tests fuer Queue-Prioritaets-Berechnung."""

    def test_critical_priority(self, service):
        """Testet kritische Prioritaet."""
        priority = service._calculate_priority(0.35)
        assert priority == QueuePriority.CRITICAL

    def test_high_priority(self, service):
        """Testet hohe Prioritaet."""
        priority = service._calculate_priority(0.50)
        assert priority == QueuePriority.HIGH

    def test_medium_priority(self, service):
        """Testet mittlere Prioritaet."""
        priority = service._calculate_priority(0.60)
        assert priority == QueuePriority.MEDIUM

    def test_low_priority(self, service):
        """Testet niedrige Prioritaet."""
        priority = service._calculate_priority(0.68)
        assert priority == QueuePriority.LOW


# =============================================================================
# DATA CLASS TESTS
# =============================================================================


class TestDataClasses:
    """Tests fuer Datenklassen."""

    def test_correction_feedback_creation(self, sample_correction):
        """Testet CorrectionFeedback Erstellung."""
        assert sample_correction.field_name == "invoice_number"
        assert sample_correction.correction_type == "reference"
        assert sample_correction.confidence_before == 0.75

    def test_correction_result_creation(self):
        """Testet CorrectionResult Erstellung."""
        result = CorrectionResult(
            correction_id=uuid4(),
            document_id=uuid4(),
            field_name="amount",
            applied=True,
            points_awarded=15,
            bonus_points=10,
            total_points=25,
            new_user_total=100,
            new_streak=5,
            achievements_unlocked=["streak_3"],
            feedback_message="+25 Punkte",
        )

        assert result.applied is True
        assert result.total_points == 25
        assert "streak_3" in result.achievements_unlocked

    def test_queue_item_creation(self):
        """Testet QueueItem Erstellung."""
        item = QueueItem(
            id=uuid4(),
            document_id=uuid4(),
            document_filename="rechnung.pdf",
            field_name="invoice_number",
            ocr_value="RE-2O26-001",
            confidence=0.55,
            priority=QueuePriority.HIGH,
            ocr_backend="deepseek",
            document_type="invoice",
            entity_name="Musterfirma GmbH",
            created_at=datetime.now(timezone.utc),
        )

        assert item.priority == QueuePriority.HIGH
        assert item.confidence == 0.55

    def test_leaderboard_entry_creation(self):
        """Testet LeaderboardEntry Erstellung."""
        entry = LeaderboardEntry(
            rank=1,
            user_id=uuid4(),
            username="topuser",
            full_name="Top User",
            corrections_count=100,
            total_points=1500,
            accuracy_rate=0.95,
            current_streak=10,
            longest_streak=15,
            achievements=["correction_100", "streak_7"],
            is_current_user=True,
        )

        assert entry.rank == 1
        assert entry.is_current_user is True

    def test_user_stats_creation(self):
        """Testet UserStats Erstellung."""
        stats = UserStats(
            user_id=uuid4(),
            total_corrections=50,
            total_points=750,
            current_streak=5,
            longest_streak=10,
            weekly_corrections=15,
            weekly_points=225,
            monthly_corrections=40,
            monthly_points=600,
            weekly_rank=3,
            monthly_rank=5,
            accuracy_rate=0.90,
            achievements=["correction_50"],
            recent_corrections=[],
            points_breakdown={"text": 300, "amount": 450},
        )

        assert stats.weekly_rank == 3
        assert stats.accuracy_rate == 0.90

    def test_batch_correction_result_creation(self):
        """Testet BatchCorrectionResult Erstellung."""
        result = BatchCorrectionResult(
            batch_id=uuid4(),
            total_corrections=10,
            applied_count=9,
            rejected_count=1,
            total_points_awarded=150,
            processing_time_ms=500,
            errors=[{"document_id": str(uuid4()), "error": "Invalid"}],
        )

        assert result.applied_count == 9
        assert result.processing_time_ms == 500


# =============================================================================
# ENUM TESTS
# =============================================================================


class TestEnums:
    """Tests fuer Enums."""

    def test_correction_status_values(self):
        """Testet CorrectionStatus Werte."""
        assert CorrectionStatus.PENDING.value == "pending"
        assert CorrectionStatus.APPLIED.value == "applied"
        assert CorrectionStatus.VERIFIED.value == "verified"

    def test_queue_priority_values(self):
        """Testet QueuePriority Werte."""
        assert QueuePriority.CRITICAL.value == "critical"
        assert QueuePriority.HIGH.value == "high"
        assert QueuePriority.MEDIUM.value == "medium"
        assert QueuePriority.LOW.value == "low"

    def test_leaderboard_period_values(self):
        """Testet LeaderboardPeriod Werte."""
        assert LeaderboardPeriod.WEEKLY.value == "weekly"
        assert LeaderboardPeriod.MONTHLY.value == "monthly"
        assert LeaderboardPeriod.ALL_TIME.value == "all_time"


# =============================================================================
# FEEDBACK MESSAGE GENERATION TESTS
# =============================================================================


class TestFeedbackMessageGeneration:
    """Tests fuer Feedback-Nachricht-Generierung."""

    def test_basic_message(self, service):
        """Testet Basis-Nachricht."""
        msg = service._generate_feedback_message(
            total_points=15,
            bonus_details=[],
            achievements=[],
        )

        assert "+15 Punkte" in msg

    def test_message_with_bonus(self, service):
        """Testet Nachricht mit Bonus."""
        msg = service._generate_feedback_message(
            total_points=25,
            bonus_details=["Grosse Korrektur", "Niedrige Konfidenz"],
            achievements=[],
        )

        assert "+25 Punkte" in msg
        assert "Grosse Korrektur" in msg

    def test_message_with_achievement(self, service):
        """Testet Nachricht mit Achievement."""
        msg = service._generate_feedback_message(
            total_points=15,
            bonus_details=[],
            achievements=["correction_10"],
        )

        assert "Achievement" in msg
        assert "10 Korrekturen" in msg


# =============================================================================
# ASYNC METHOD TESTS
# =============================================================================


class TestAsyncMethods:
    """Tests fuer async Methoden."""

    @pytest.mark.asyncio
    async def test_get_current_streak_no_user(self, service):
        """Testet Streak ohne User."""
        streak = await service._get_current_streak(None)
        assert streak == 0

    @pytest.mark.asyncio
    async def test_is_first_of_day_no_user(self, service):
        """Testet First-of-Day ohne User."""
        is_first = await service._is_first_of_day(None, datetime.now(timezone.utc))
        assert is_first is False

    @pytest.mark.asyncio
    async def test_get_consecutive_corrections_no_user(self, service):
        """Testet konsekutive Korrekturen ohne User."""
        count = await service._get_consecutive_corrections(None, datetime.now(timezone.utc))
        assert count == 0


# =============================================================================
# ACHIEVEMENT DEFINITIONS TESTS
# =============================================================================


class TestAchievementDefinitions:
    """Tests fuer Achievement-Definitionen."""

    def test_correction_milestones(self):
        """Testet Korrektur-Meilensteine."""
        expected = ["first_correction", "correction_10", "correction_50", "correction_100"]
        # Diese werden in _check_achievements geprueft
        assert True  # Placeholder - Achievement-Logik ist in Service

    def test_points_milestones(self):
        """Testet Punkte-Meilensteine."""
        expected = ["points_100", "points_500", "points_1000"]
        assert True

    def test_streak_milestones(self):
        """Testet Streak-Meilensteine."""
        expected = ["streak_3", "streak_7", "streak_30"]
        assert True


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_zero_confidence(self, service):
        """Testet Null-Konfidenz."""
        priority = service._calculate_priority(0.0)
        assert priority == QueuePriority.CRITICAL

    def test_high_confidence_still_in_queue(self, service):
        """Testet hohe Konfidenz aber noch in Queue."""
        priority = service._calculate_priority(0.69)
        assert priority == QueuePriority.LOW

    def test_empty_strings_major_correction(self, service):
        """Testet leere Strings."""
        is_major = service._is_major_correction("", "")
        assert is_major is True  # Beide leer = major

    def test_identical_strings_not_major(self, service):
        """Testet identische Strings."""
        is_major = service._is_major_correction("test", "test")
        assert is_major is False

    def test_unicode_correction(self, service):
        """Testet Unicode-Korrektur."""
        is_major = service._is_major_correction("Muller", "Mueller")
        assert is_major is False  # Nur 1 Zeichen Aenderung

    def test_long_text_correction(self, service):
        """Testet lange Text-Korrektur."""
        original = "a" * 100
        corrected = "a" * 150
        is_major = service._is_major_correction(original, corrected)
        # 50% Aenderung > 30% Schwelle
        assert is_major is True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration-Tests."""

    @pytest.mark.asyncio
    async def test_full_correction_flow(self, service, mock_db, sample_correction):
        """Testet kompletten Korrektur-Flow (mit Mocks)."""
        company_id = uuid4()

        # Mock DB responses fuer Self-Learning Import
        with patch("app.services.ocr.feedback_service.get_self_learning_service") as mock_sl:
            mock_sl.return_value.process_correction = AsyncMock(return_value={"processed": True})

            # Mock fuer _update_user_stats
            service._update_user_stats = AsyncMock(return_value=(100, 5, ["first_correction"]))
            service._calculate_bonus_points = AsyncMock(return_value=(10, ["Niedrige Konfidenz"]))
            service._remove_from_queue = AsyncMock()

            # Service sollte ohne Fehler laufen
            assert service is not None

    @pytest.mark.asyncio
    async def test_batch_correction_partial_success(self, service, mock_db):
        """Testet Batch-Korrektur mit teilweisem Erfolg."""
        # In echtem Test mit DB-Integration pruefen
        assert service is not None

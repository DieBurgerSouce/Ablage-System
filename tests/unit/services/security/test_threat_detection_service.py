# -*- coding: utf-8 -*-
"""Unit tests for ThreatDetectionService."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.security.threat_detection_service import (
    ThreatDetectionService,
    ThreatIndicator,
    SecurityReport,
    get_threat_detection_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> ThreatDetectionService:
    return ThreatDetectionService()


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    return db


def _make_activity(
    user_id: int,
    activity_type: str = "view",
    hour: int = 10,
    minutes_offset: int = 0,
) -> MagicMock:
    """Helper to create a fake DocumentActivity."""
    activity = MagicMock()
    activity.user_id = user_id
    activity.activity_type = activity_type
    activity.created_at = datetime(
        2026, 3, 10, hour, minutes_offset, 0, tzinfo=timezone.utc
    )
    return activity


# ---------------------------------------------------------------------------
# ThreatIndicator dataclass
# ---------------------------------------------------------------------------


class TestThreatIndicator:
    def test_creation_with_defaults(self) -> None:
        indicator = ThreatIndicator(
            indicator_type="access_anomaly",
            severity="hoch",
            description="Verdaechtiger Zugriff",
        )
        assert indicator.indicator_type == "access_anomaly"
        assert indicator.severity == "hoch"
        assert indicator.description == "Verdaechtiger Zugriff"
        assert indicator.user_id is None
        assert indicator.details == {}
        # detected_at should be an ISO timestamp string
        assert "T" in indicator.detected_at

    def test_creation_with_all_fields(self) -> None:
        indicator = ThreatIndicator(
            indicator_type="exfiltration",
            severity="kritisch",
            description="Massen-Export",
            user_id=42,
            detected_at="2026-03-10T12:00:00+00:00",
            details={"count": 100},
        )
        assert indicator.user_id == 42
        assert indicator.details["count"] == 100

    def test_asdict(self) -> None:
        indicator = ThreatIndicator(
            indicator_type="test",
            severity="niedrig",
            description="Test",
        )
        d = asdict(indicator)
        assert isinstance(d, dict)
        assert d["indicator_type"] == "test"


# ---------------------------------------------------------------------------
# SecurityReport dataclass
# ---------------------------------------------------------------------------


class TestSecurityReport:
    def test_creation_with_defaults(self) -> None:
        report = SecurityReport(
            period="woche",
            gesamtrisiko="niedrig",
            anomalie_count=0,
        )
        assert report.period == "woche"
        assert report.gesamtrisiko == "niedrig"
        assert report.anomalie_count == 0
        assert report.top_risiken == []
        assert report.empfehlungen == []
        assert "T" in report.generated_at

    def test_creation_with_all_fields(self) -> None:
        report = SecurityReport(
            period="monat",
            gesamtrisiko="kritisch",
            anomalie_count=15,
            top_risiken=[{"typ": "bulk_downloads", "schwere": "hoch"}],
            empfehlungen=["Sofortige Sperrung"],
        )
        assert len(report.top_risiken) == 1
        assert len(report.empfehlungen) == 1


# ---------------------------------------------------------------------------
# ThreatDetectionService constants
# ---------------------------------------------------------------------------


class TestServiceConstants:
    def test_normal_work_hours(self) -> None:
        assert ThreatDetectionService.NORMAL_WORK_HOURS == (8, 18)

    def test_max_downloads_per_hour(self) -> None:
        assert ThreatDetectionService.MAX_DOWNLOADS_PER_HOUR == 50

    def test_max_exports_per_hour(self) -> None:
        assert ThreatDetectionService.MAX_EXPORTS_PER_HOUR == 20

    def test_bulk_download_threshold(self) -> None:
        assert ThreatDetectionService.BULK_DOWNLOAD_THRESHOLD == 10

    def test_failed_access_threshold(self) -> None:
        assert ThreatDetectionService.FAILED_ACCESS_THRESHOLD == 5

    def test_risk_weights_exist(self) -> None:
        weights = ThreatDetectionService.RISK_WEIGHTS
        assert "after_hours_access" in weights
        assert "bulk_downloads" in weights
        assert "failed_access" in weights


# ---------------------------------------------------------------------------
# analyze_access_patterns
# ---------------------------------------------------------------------------


class TestAnalyzeAccessPatterns:
    @pytest.mark.asyncio
    async def test_empty_activities_returns_niedrig(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        """No activities should yield threat_level 'niedrig'."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.analyze_access_patterns(mock_db, company_id=1)

        assert result["threat_level"] == "niedrig"
        assert result["anomalies"] == []
        assert result["user_risk_scores"] == {}
        assert result["analyzed_activities"] == 0
        assert result["period_hours"] == 24

    @pytest.mark.asyncio
    async def test_returns_dict_structure(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        """Return value must have the expected keys."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=48)

        expected_keys = {
            "threat_level",
            "anomalies",
            "user_risk_scores",
            "analyzed_activities",
            "analyzed_users",
            "period_hours",
        }
        assert set(result.keys()) == expected_keys
        assert result["period_hours"] == 48

    @pytest.mark.asyncio
    async def test_after_hours_anomaly_detected(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        """More than 5 after-hours accesses should create an anomaly."""
        # Create 7 after-hours activities (hour=22 is outside 8-18)
        activities = [_make_activity(user_id=1, hour=22, minutes_offset=i) for i in range(7)]

        # First execute: activity query
        activity_result = MagicMock()
        activity_result.scalars.return_value.all.return_value = activities

        # Second execute: audit log query (failed access count) - returns 0
        audit_result = MagicMock()
        audit_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[activity_result, audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1)

        assert len(result["anomalies"]) >= 1
        anomaly_types = [a["indicator_type"] for a in result["anomalies"]]
        assert "after_hours_access" in anomaly_types
        assert result["threat_level"] in ("mittel", "hoch", "kritisch")

    @pytest.mark.asyncio
    async def test_no_anomaly_within_work_hours(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        """Activities within work hours should not trigger after-hours anomaly."""
        activities = [_make_activity(user_id=1, hour=10, minutes_offset=i) for i in range(3)]

        activity_result = MagicMock()
        activity_result.scalars.return_value.all.return_value = activities

        audit_result = MagicMock()
        audit_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[activity_result, audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1)

        after_hours_anomalies = [
            a for a in result["anomalies"] if a["indicator_type"] == "after_hours_access"
        ]
        assert len(after_hours_anomalies) == 0

    @pytest.mark.asyncio
    async def test_db_exception_propagates(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        """Database failure should propagate the exception."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        with pytest.raises(Exception, match="DB connection lost"):
            await service.analyze_access_patterns(mock_db, company_id=1)

    @pytest.mark.asyncio
    async def test_custom_hours_parameter(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=168)

        assert result["period_hours"] == 168


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_threat_detection_service_returns_instance(self) -> None:
        svc = get_threat_detection_service()
        assert isinstance(svc, ThreatDetectionService)

    def test_get_threat_detection_service_returns_same_instance(self) -> None:
        svc1 = get_threat_detection_service()
        svc2 = get_threat_detection_service()
        assert svc1 is svc2

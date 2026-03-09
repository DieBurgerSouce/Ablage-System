# -*- coding: utf-8 -*-
"""
Tests fuer ThreatDetectionService.

Testet:
- Zugriffsmuster-Analyse
- Datenexfiltrationserkennung
- Insider-Threat-Scoring
- Permission-Anomalie-Erkennung
- Sicherheitsberichterstattung
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from dataclasses import asdict

from app.services.security.threat_detection_service import (
    ThreatDetectionService,
    ThreatIndicator,
    SecurityReport,
    get_threat_detection_service,
)


@pytest.fixture
def service() -> ThreatDetectionService:
    """Erstellt eine ThreatDetectionService-Instanz."""
    return ThreatDetectionService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock()
    return db


def _make_activity(
    user_id: int,
    activity_type: str = "view",
    hour: int = 10,
    created_at: datetime = None,
) -> Mock:
    """Erzeugt ein Mock-DocumentActivity-Objekt."""
    activity = Mock()
    activity.user_id = user_id
    activity.activity_type = activity_type
    if created_at is None:
        created_at = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0)
    activity.created_at = created_at
    return activity


class TestThreatIndicator:
    """Tests fuer das ThreatIndicator-Dataclass."""

    def test_erstellt_mit_standardwerten(self):
        """ThreatIndicator wird mit korrekten Standardwerten erstellt."""
        indicator = ThreatIndicator(
            indicator_type="test_type",
            severity="mittel",
            description="Testbeschreibung",
        )
        assert indicator.indicator_type == "test_type"
        assert indicator.severity == "mittel"
        assert indicator.user_id is None
        assert indicator.details == {}
        assert indicator.detected_at is not None

    def test_serialisierung_zu_dict(self):
        """ThreatIndicator kann zu Dict serialisiert werden."""
        indicator = ThreatIndicator(
            indicator_type="access_anomaly",
            severity="hoch",
            description="Ungewoehnlicher Zugriff",
            user_id=42,
            details={"count": 10},
        )
        d = asdict(indicator)
        assert d["indicator_type"] == "access_anomaly"
        assert d["user_id"] == 42
        assert d["details"]["count"] == 10


class TestAnalyzeAccessPatterns:
    """Tests fuer analyze_access_patterns()."""

    @pytest.mark.asyncio
    async def test_keine_aktivitaeten_ergibt_niedrig(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Ohne Aktivitaeten ist threat_level 'niedrig'."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=24)

        assert result["threat_level"] == "niedrig"
        assert result["anomalies"] == []
        assert result["analyzed_activities"] == 0

    @pytest.mark.asyncio
    async def test_after_hours_zugriff_erkennung(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Zugriffe ausserhalb der Arbeitszeiten werden erkannt."""
        # 10 Zugriffe um 3 Uhr nachts
        activities = [
            _make_activity(user_id=1, hour=3) for _ in range(10)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        # Fuer AuditLog-Abfrage
        mock_audit_result = MagicMock()
        mock_audit_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=24)

        assert len(result["anomalies"]) > 0
        anomaly_types = [a["indicator_type"] for a in result["anomalies"]]
        assert "after_hours_access" in anomaly_types

    @pytest.mark.asyncio
    async def test_bulk_downloads_erkennung(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Massen-Downloads innerhalb von 5 Minuten werden erkannt."""
        base_time = datetime.now(timezone.utc).replace(hour=10)
        activities = []
        for i in range(12):
            activities.append(
                _make_activity(
                    user_id=1,
                    activity_type="download",
                    created_at=base_time + timedelta(seconds=i * 10),
                )
            )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        mock_audit_result = MagicMock()
        mock_audit_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=24)

        anomaly_types = [a["indicator_type"] for a in result["anomalies"]]
        assert "bulk_downloads" in anomaly_types

    @pytest.mark.asyncio
    async def test_failed_access_erkennung(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Wiederholte Fehlzugriffe werden erkannt."""
        activities = [_make_activity(user_id=1, hour=10)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        mock_audit_result = MagicMock()
        mock_audit_result.scalar.return_value = 10  # Ueber Schwellwert

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=24)

        anomaly_types = [a["indicator_type"] for a in result["anomalies"]]
        assert "failed_access" in anomaly_types

    @pytest.mark.asyncio
    async def test_risiko_score_begrenzt_auf_eins(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Risiko-Score wird auf maximal 1.0 begrenzt."""
        # Viele Anomalien gleichzeitig
        base_time = datetime.now(timezone.utc).replace(hour=3)
        activities = []
        for i in range(15):
            activities.append(
                _make_activity(
                    user_id=1,
                    activity_type="download",
                    created_at=base_time + timedelta(seconds=i * 5),
                )
            )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        mock_audit_result = MagicMock()
        mock_audit_result.scalar.return_value = 20

        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_audit_result])

        result = await service.analyze_access_patterns(mock_db, company_id=1, hours=24)

        for score in result["user_risk_scores"].values():
            assert score <= 1.0


class TestDetectDataExfiltration:
    """Tests fuer detect_data_exfiltration()."""

    @pytest.mark.asyncio
    async def test_keine_exfiltration_bei_normaler_nutzung(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Normale Nutzung ergibt kein Exfiltrationsrisiko."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.detect_data_exfiltration(mock_db, company_id=1)

        assert result["exfiltration_risk"] == 0.0
        assert result["indicators"] == []

    @pytest.mark.asyncio
    async def test_massen_export_erkennung(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Massen-Exports werden als Exfiltrationsversuch erkannt."""
        activities = []
        for _ in range(50):
            act = _make_activity(user_id=1, activity_type="export", hour=10)
            activities.append(act)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.detect_data_exfiltration(mock_db, company_id=1)

        assert result["exfiltration_risk"] > 0.0
        indicator_types = [i["indicator_type"] for i in result["indicators"]]
        assert "mass_export" in indicator_types

    @pytest.mark.asyncio
    async def test_empfehlungen_bei_hohem_risiko(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Bei hohem Risiko werden Sofortmassnahmen empfohlen."""
        activities = []
        base_time = datetime.now(timezone.utc).replace(hour=3)
        for _ in range(100):
            act = _make_activity(user_id=1, activity_type="export", created_at=base_time)
            activities.append(act)
        for _ in range(200):
            act = _make_activity(user_id=1, activity_type="download", created_at=base_time)
            activities.append(act)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = activities
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.detect_data_exfiltration(mock_db, company_id=1)

        assert result["exfiltration_risk"] >= 0.7
        assert len(result["recommended_actions"]) > 0


class TestGetInsiderThreatScore:
    """Tests fuer get_insider_threat_score()."""

    @pytest.mark.asyncio
    async def test_niedriger_score_bei_normaler_aktivitaet(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Normale Aktivitaet ergibt niedrigen Insider-Threat-Score."""
        # Alle DB-Abfragen geben niedrige Werte zurueck
        mock_db.execute = AsyncMock(
            side_effect=[
                AsyncMock(scalar=Mock(return_value=10)),   # Aktivitaeten
                AsyncMock(scalar=Mock(return_value=0)),    # After-hours
                AsyncMock(scalar=Mock(return_value=0)),    # Fehlzugriffe
                AsyncMock(scalar=Mock(return_value=0)),    # Exports
            ]
        )

        result = await service.get_insider_threat_score(mock_db, company_id=1, user_id=1)

        assert result["risk_score"] == 0.0
        assert result["risk_level"] == "niedrig"
        assert result["contributing_factors"] == []

    @pytest.mark.asyncio
    async def test_hoher_score_bei_verdaechtigem_verhalten(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Verdaechtiges Verhalten ergibt hohen Score."""
        mock_db.execute = AsyncMock(
            side_effect=[
                AsyncMock(scalar=Mock(return_value=300)),   # Viele Aktivitaeten
                AsyncMock(scalar=Mock(return_value=50)),    # Viele After-hours
                AsyncMock(scalar=Mock(return_value=20)),    # Viele Fehlzugriffe
                AsyncMock(scalar=Mock(return_value=30)),    # Viele Exports
            ]
        )

        result = await service.get_insider_threat_score(mock_db, company_id=1, user_id=1)

        assert result["risk_score"] > 0.5
        assert result["risk_level"] in ("hoch", "kritisch")
        assert len(result["contributing_factors"]) > 0


class TestCheckPermissionAnomalies:
    """Tests fuer check_permission_anomalies()."""

    @pytest.mark.asyncio
    async def test_keine_anomalien(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Ohne Permission-Aenderungen gibt es keine Anomalien."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_permission_anomalies(mock_db, company_id=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_haeufige_permission_aenderungen(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Haeufige Permission-Aenderungen werden als Anomalie erkannt."""
        logs = []
        for i in range(15):
            log = Mock()
            log.user_id = 1
            log.action = "permission_changed"
            log.created_at = datetime.now(timezone.utc)
            logs.append(log)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = logs
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_permission_anomalies(mock_db, company_id=1)

        assert len(result) > 0
        assert result[0]["anomaly_type"] == "frequent_permission_changes"

    @pytest.mark.asyncio
    async def test_escalation_versuche(
        self, service: ThreatDetectionService, mock_db: AsyncMock
    ):
        """Escalation-Versuche werden als Anomalie erkannt."""
        logs = []
        for i in range(5):
            log = Mock()
            log.user_id = 1
            log.action = "grant_admin_role"
            log.created_at = datetime.now(timezone.utc)
            logs.append(log)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = logs
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_permission_anomalies(mock_db, company_id=1)

        anomaly_types = [a["anomaly_type"] for a in result]
        assert "permission_escalation" in anomaly_types


class TestGetThreatDetectionServiceSingleton:
    """Tests fuer die Singleton-Factory."""

    def test_singleton_gibt_gleiche_instanz_zurueck(self):
        """get_threat_detection_service() gibt immer dieselbe Instanz zurueck."""
        import app.services.security.threat_detection_service as module
        module._service = None  # Reset

        s1 = get_threat_detection_service()
        s2 = get_threat_detection_service()

        assert s1 is s2

        module._service = None  # Cleanup

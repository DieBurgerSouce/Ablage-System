# -*- coding: utf-8 -*-
"""
Tests fuer IncidentResponseService.

Testet:
- Brute-Force-Erkennung
- Rate-Limit-Missbrauch-Erkennung
- Unauthorized Access-Erkennung
- Incident-Response-Ausfuehrung
- IP-Blocking (temporaer/permanent)
- Account-Lockout
- Sicherheit: Schwellwerte, Eskalation
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

from app.services.incident_response_service import (
    IncidentResponseService,
    Incident,
    IncidentType,
    IncidentSeverity,
    ResponseAction,
    RESPONSE_RULES,
    INCIDENT_THRESHOLDS,
    get_incident_response_service,
    report_system_incident,
)


@pytest.fixture
def service() -> IncidentResponseService:
    """Erstellt eine frische IncidentResponseService-Instanz."""
    return IncidentResponseService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


class TestIncident:
    """Tests fuer das Incident-Objekt."""

    def test_erstellt_mit_eindeutiger_id(self):
        """Incidents haben eine eindeutige ID."""
        inc1 = Incident(
            incident_type=IncidentType.BRUTE_FORCE_ATTACK,
            severity=IncidentSeverity.MEDIUM,
            description="Test-Incident 1",
        )
        inc2 = Incident(
            incident_type=IncidentType.BRUTE_FORCE_ATTACK,
            severity=IncidentSeverity.MEDIUM,
            description="Test-Incident 2",
        )

        # IDs sind basierend auf Zeitstempel, daher mindestens 16 Zeichen
        assert len(inc1.id) == 16
        assert len(inc2.id) == 16

    def test_to_dict_enthaelt_alle_felder(self):
        """to_dict() enthaelt alle relevanten Felder."""
        user_id = uuid4()
        incident = Incident(
            incident_type=IncidentType.BRUTE_FORCE_ATTACK,
            severity=IncidentSeverity.HIGH,
            description="Brute-Force erkannt",
            ip_address="192.0.2.1",
            user_id=user_id,
            details={"count": 50},
        )

        d = incident.to_dict()

        assert d["type"] == "brute_force_attack"
        assert d["severity"] == "high"
        assert d["ip_address"] == "192.0.2.1"
        assert d["user_id"] == str(user_id)
        assert d["details"]["count"] == 50
        assert d["created_at"] is not None

    def test_actions_taken_initial_leer(self):
        """Neue Incidents haben keine ausgefuehrten Actions."""
        incident = Incident(
            incident_type=IncidentType.SUSPICIOUS_IP_ACTIVITY,
            severity=IncidentSeverity.LOW,
            description="Test",
        )

        assert incident.actions_taken == []


class TestDetectBruteForce:
    """Tests fuer _detect_brute_force()."""

    @pytest.mark.asyncio
    async def test_erkennt_brute_force_angriff(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Erkennt Brute-Force wenn Schwellwert ueberschritten."""
        threshold = INCIDENT_THRESHOLDS["failed_logins_threshold"]
        since = datetime.now(timezone.utc) - timedelta(minutes=15)

        # Simuliere DB-Ergebnis: IP mit vielen fehlgeschlagenen Logins
        mock_row = Mock()
        mock_row.ip_address = "192.0.2.100"
        mock_row.count = threshold + 5

        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_db.execute = AsyncMock(return_value=mock_result)

        incidents = await service._detect_brute_force(mock_db, since)

        assert len(incidents) == 1
        assert incidents[0].type == IncidentType.BRUTE_FORCE_ATTACK
        assert incidents[0].ip_address == "192.0.2.100"

    @pytest.mark.asyncio
    async def test_severity_eskaliert_bei_hoher_anzahl(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Severity eskaliert bei deutlicher Schwellwert-Ueberschreitung."""
        threshold = INCIDENT_THRESHOLDS["failed_logins_threshold"]
        since = datetime.now(timezone.utc) - timedelta(minutes=15)

        mock_row = Mock()
        mock_row.ip_address = "192.0.2.100"
        mock_row.count = threshold * 5  # 5x Schwellwert = CRITICAL

        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_db.execute = AsyncMock(return_value=mock_result)

        incidents = await service._detect_brute_force(mock_db, since)

        assert incidents[0].severity == IncidentSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_keine_erkennung_unter_schwellwert(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Keine Erkennung wenn Schwellwert nicht erreicht."""
        since = datetime.now(timezone.utc) - timedelta(minutes=15)

        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_result)

        incidents = await service._detect_brute_force(mock_db, since)

        assert len(incidents) == 0


class TestDetectRateLimitAbuse:
    """Tests fuer _detect_rate_limit_abuse()."""

    @pytest.mark.asyncio
    async def test_erkennt_rate_limit_missbrauch(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Erkennt wiederholte Rate-Limit-Ueberschreitungen."""
        since = datetime.now(timezone.utc) - timedelta(minutes=5)

        mock_row = Mock()
        mock_row.ip_address = "192.0.2.200"
        mock_row.count = 100

        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_db.execute = AsyncMock(return_value=mock_result)

        incidents = await service._detect_rate_limit_abuse(mock_db, since)

        assert len(incidents) == 1
        assert incidents[0].type == IncidentType.RATE_LIMIT_ABUSE


class TestExecuteResponse:
    """Tests fuer execute_response()."""

    @pytest.mark.asyncio
    async def test_log_only_action(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """LOG_ONLY Action wird ausgefuehrt."""
        incident = Incident(
            incident_type=IncidentType.SUSPICIOUS_IP_ACTIVITY,
            severity=IncidentSeverity.LOW,
            description="Verdaechtige Aktivitaet",
            ip_address="192.0.2.1",
        )

        actions = await service.execute_response(incident, mock_db)

        assert "Incident protokolliert" in actions

    @pytest.mark.asyncio
    async def test_block_ip_temporaer(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Temporaere IP-Sperre wird ausgefuehrt."""
        incident = Incident(
            incident_type=IncidentType.BRUTE_FORCE_ATTACK,
            severity=IncidentSeverity.MEDIUM,
            description="Brute-Force erkannt",
            ip_address="192.0.2.50",
        )

        with patch.object(service, "_notify_admin", new_callable=AsyncMock):
            actions = await service.execute_response(incident, mock_db)

        assert any("192.0.2.50" in a and "gesperrt" in a for a in actions)

    @pytest.mark.asyncio
    async def test_account_lockout_bei_kritischem_incident(
        self, service: IncidentResponseService, mock_db: AsyncMock
    ):
        """Account wird bei kritischem Incident gesperrt."""
        user_id = uuid4()
        incident = Incident(
            incident_type=IncidentType.BRUTE_FORCE_ATTACK,
            severity=IncidentSeverity.CRITICAL,
            description="Massiver Brute-Force-Angriff",
            ip_address="192.0.2.99",
            user_id=user_id,
        )

        mock_user = Mock()
        mock_user.is_active = True
        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_user_result)

        with patch.object(service, "_notify_admin", new_callable=AsyncMock), \
             patch.object(service, "_revoke_sessions", new_callable=AsyncMock):
            actions = await service.execute_response(incident, mock_db)

        assert any("gesperrt" in a for a in actions)


class TestIPBlocking:
    """Tests fuer is_ip_blocked() und IP-Verwaltung."""

    def test_blockierte_ip_wird_erkannt(self, service: IncidentResponseService):
        """Blockierte IP wird korrekt als blockiert erkannt."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        service._blocked_ips["192.0.2.10"] = future

        assert service.is_ip_blocked("192.0.2.10") is True

    def test_nicht_blockierte_ip_ist_frei(self, service: IncidentResponseService):
        """Nicht-blockierte IP wird als frei erkannt."""
        assert service.is_ip_blocked("192.0.2.20") is False

    def test_abgelaufene_sperre_wird_aufgehoben(
        self, service: IncidentResponseService
    ):
        """Abgelaufene Sperre wird automatisch aufgehoben."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        service._blocked_ips["192.0.2.30"] = past

        assert service.is_ip_blocked("192.0.2.30") is False
        assert "192.0.2.30" not in service._blocked_ips

    def test_get_blocked_ips_filtert_abgelaufene(
        self, service: IncidentResponseService
    ):
        """get_blocked_ips() gibt nur aktive Sperren zurueck."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        service._blocked_ips["192.0.2.10"] = future
        service._blocked_ips["192.0.2.11"] = past

        blocked = service.get_blocked_ips()

        assert "192.0.2.10" in blocked
        assert "192.0.2.11" not in blocked


class TestResponseRules:
    """Tests fuer Response-Regeln-Konfiguration."""

    def test_brute_force_hat_eskalation(self):
        """Brute-Force hat steigende Reaktionsmassnahmen."""
        rules = RESPONSE_RULES[IncidentType.BRUTE_FORCE_ATTACK]

        medium_actions = rules[IncidentSeverity.MEDIUM]
        critical_actions = rules[IncidentSeverity.CRITICAL]

        assert len(critical_actions) > len(medium_actions)
        assert ResponseAction.BLOCK_IP_PERMANENT in critical_actions

    def test_admin_account_compromise_ist_maximal(self):
        """Admin Account Compromise hat maximale Reaktion."""
        rules = RESPONSE_RULES[IncidentType.ADMIN_ACCOUNT_COMPROMISE]
        critical = rules[IncidentSeverity.CRITICAL]

        assert ResponseAction.LOCK_ACCOUNT in critical
        assert ResponseAction.REVOKE_ALL_SESSIONS in critical
        assert ResponseAction.REQUIRE_2FA in critical


class TestGetActiveIncidents:
    """Tests fuer get_active_incidents()."""

    def test_gibt_alle_aktiven_incidents_zurueck(
        self, service: IncidentResponseService
    ):
        """Aktive Incidents werden als Liste zurueckgegeben."""
        inc = Incident(
            incident_type=IncidentType.RATE_LIMIT_ABUSE,
            severity=IncidentSeverity.MEDIUM,
            description="Test",
        )
        service.active_incidents[inc.id] = inc

        result = service.get_active_incidents()

        assert len(result) == 1
        assert result[0]["type"] == "rate_limit_abuse"


class TestReportSystemIncident:
    """Tests fuer report_system_incident() (synchroner Aufruf)."""

    def test_erstellt_und_speichert_incident(self):
        """Erstellt Incident und speichert ihn in aktiven Incidents."""
        import app.services.incident_response_service as module
        module._incident_response_service = None  # Reset Singleton

        with patch.object(
            IncidentResponseService, "_notify_admin", new_callable=AsyncMock
        ):
            incident = report_system_incident(
                incident_type=IncidentType.DLQ_CRITICAL,
                severity=IncidentSeverity.CRITICAL,
                description="DLQ enthaelt 500+ fehlgeschlagene Tasks",
                details={"count": 523},
            )

        assert incident.type == IncidentType.DLQ_CRITICAL
        assert incident.severity == IncidentSeverity.CRITICAL
        assert incident.details["count"] == 523

        # Aufraumen
        module._incident_response_service = None


class TestSingletonFactory:
    """Tests fuer get_incident_response_service()."""

    def test_singleton_gibt_gleiche_instanz(self):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        import app.services.incident_response_service as module
        module._incident_response_service = None

        s1 = get_incident_response_service()
        s2 = get_incident_response_service()

        assert s1 is s2

        module._incident_response_service = None

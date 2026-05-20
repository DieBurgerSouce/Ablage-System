# -*- coding: utf-8 -*-
"""
Tests fuer Trust Dashboard Service.

Testet Trust/Security Dashboard für Compliance:
- Dashboard Snapshots
- Zugriffsprotokolle
- Export-Logs
- Anomalie-Erkennung
- Compliance-Score
- Security-Events
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from typing import List, Dict, Any

from app.services.trust_dashboard_service import TrustDashboardService
from app.db.models import AuditLog, Document, User


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    return AsyncMock()


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Test User-ID."""
    return uuid4()


@pytest.fixture
def dashboard_service(mock_db):
    """Fixture fuer TrustDashboardService."""
    return TrustDashboardService(session=mock_db)


# =============================================================================
# Dashboard Snapshot Tests
# =============================================================================


class TestGetDashboardSnapshot:
    """Tests fuer get_dashboard_snapshot."""

    @pytest.mark.asyncio
    async def test_snapshot_structure(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Dashboard Snapshot hat korrekte Struktur."""
        # Mock all queries
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=0))

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        assert "period_days" in snapshot
        assert snapshot["period_days"] == 30
        assert "period_start" in snapshot
        assert "period_end" in snapshot
        assert "metrics" in snapshot
        assert "recent_security_events" in snapshot
        assert "top_accessed_documents" in snapshot
        assert "user_activity_summary" in snapshot

    @pytest.mark.asyncio
    async def test_metrics_structure(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Metrics haben korrekte Struktur."""
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=0))

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        metrics = snapshot["metrics"]
        assert "total_accesses" in metrics
        assert "sensitive_accesses" in metrics
        assert "export_count" in metrics
        assert "anomaly_count" in metrics
        assert "compliance_score" in metrics

    @pytest.mark.asyncio
    async def test_metrics_values_with_activity(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Metrics mit Aktivitaet haben korrekte Werte."""
        # Mock queries with actual values
        query_results = [
            MagicMock(scalar=MagicMock(return_value=100)),  # total_accesses
            MagicMock(scalar=MagicMock(return_value=25)),   # sensitive_accesses
            MagicMock(scalar=MagicMock(return_value=10)),   # export_count
            MagicMock(scalar=MagicMock(return_value=5)),    # anomaly_count
            MagicMock(scalar=MagicMock(return_value=2)),    # error_count for compliance
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),  # events
            MagicMock(all=MagicMock(return_value=[])),      # top_documents
            MagicMock(all=MagicMock(return_value=[])),      # user_activity
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        metrics = snapshot["metrics"]
        assert metrics["total_accesses"] == 100
        assert metrics["sensitive_accesses"] == 25
        assert metrics["export_count"] == 10
        assert metrics["anomaly_count"] == 5
        assert 0 <= metrics["compliance_score"] <= 100

    @pytest.mark.asyncio
    async def test_empty_database_returns_zero_metrics(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Leere DB = Metriken mit 0."""
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=0))

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        metrics = snapshot["metrics"]
        assert metrics["total_accesses"] == 0
        assert metrics["sensitive_accesses"] == 0
        assert metrics["export_count"] == 0
        assert metrics["anomaly_count"] == 0
        assert metrics["compliance_score"] == 100.0  # Perfect score with no errors

    @pytest.mark.asyncio
    async def test_compliance_score_calculation(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Compliance-Score berechnet korrekt (0-100)."""
        # 1000 accesses, 50 anomalies (5%), 20 errors (2%)
        query_results = [
            MagicMock(scalar=MagicMock(return_value=1000)),  # total_accesses
            MagicMock(scalar=MagicMock(return_value=100)),   # sensitive_accesses
            MagicMock(scalar=MagicMock(return_value=50)),    # export_count
            MagicMock(scalar=MagicMock(return_value=50)),    # anomaly_count
            MagicMock(scalar=MagicMock(return_value=20)),    # error_count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        score = snapshot["metrics"]["compliance_score"]
        assert 0 <= score <= 100
        # With 5% anomaly rate and 2% error rate, should be < 100
        assert score < 100

    @pytest.mark.asyncio
    async def test_period_filtering(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Period-Filter wird korrekt angewendet."""
        days = 7
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=0))

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=days)

        assert snapshot["period_days"] == days
        period_start = datetime.fromisoformat(snapshot["period_start"])
        period_end = datetime.fromisoformat(snapshot["period_end"])
        delta = period_end - period_start
        assert delta.days >= days - 1  # Allow slight timing variation

    @pytest.mark.asyncio
    async def test_recent_security_events(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Recent security events werden geladen."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.action = "login_failed"
        mock_log.user_id = uuid4()
        mock_log.resource_type = "user"
        mock_log.resource_id = None
        mock_log.ip_address = "192.168.1.1"
        mock_log.success = False
        mock_log.error_message = "Invalid credentials"
        mock_log.created_at = datetime.now(timezone.utc)

        query_results = [
            MagicMock(scalar=MagicMock(return_value=0)),  # total_accesses
            MagicMock(scalar=MagicMock(return_value=0)),  # sensitive_accesses
            MagicMock(scalar=MagicMock(return_value=0)),  # export_count
            MagicMock(scalar=MagicMock(return_value=0)),  # anomaly_count
            MagicMock(scalar=MagicMock(return_value=0)),  # error_count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_log])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        events = snapshot["recent_security_events"]
        assert len(events) == 1
        assert events[0]["action"] == "login_failed"
        assert events[0]["success"] is False

    @pytest.mark.asyncio
    async def test_top_accessed_documents(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Top-Dokumente werden geladen."""
        doc_id = uuid4()
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = doc_id
        mock_doc.filename = "important_doc.pdf"

        query_results = [
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[(doc_id, 50)])),  # doc_id, access_count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_doc])))),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        top_docs = snapshot["top_accessed_documents"]
        assert len(top_docs) == 1
        assert top_docs[0]["document_id"] == str(doc_id)
        assert top_docs[0]["access_count"] == 50
        assert top_docs[0]["filename"] == "important_doc.pdf"

    @pytest.mark.asyncio
    async def test_user_activity_summary(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: User Activity Summary wird erstellt."""
        user_id = uuid4()
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.username = "testuser"

        query_results = [
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[(user_id, 75)])),  # user_id, action_count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_user])))),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        user_activity = snapshot["user_activity_summary"]
        assert "top_users" in user_activity
        assert len(user_activity["top_users"]) == 1
        assert user_activity["top_users"][0]["user_id"] == str(user_id)
        assert user_activity["top_users"][0]["username"] == "testuser"
        assert user_activity["top_users"][0]["action_count"] == 75


# =============================================================================
# Access Log Tests
# =============================================================================


class TestGetAccessLog:
    """Tests fuer get_access_log."""

    @pytest.mark.asyncio
    async def test_returns_access_log_list(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Gibt Liste von Access-Logs zurueck."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "document_view"
        mock_log.resource_type = "document"
        mock_log.resource_id = uuid4()
        mock_log.ip_address = "192.168.1.1"
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_access_log(company_id, days=30)

        assert isinstance(logs, list)
        assert len(logs) == 1
        assert logs[0]["action"] == "document_view"

    @pytest.mark.asyncio
    async def test_access_log_correct_fields(
        self,
        dashboard_service,
        mock_db,
        company_id,
        user_id,
    ):
        """Test: Access Log hat korrekte Felder."""
        resource_id = uuid4()
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = user_id
        mock_log.action = "document_download"
        mock_log.resource_type = "document"
        mock_log.resource_id = resource_id
        mock_log.ip_address = "10.0.0.1"
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_access_log(company_id, days=30)

        log = logs[0]
        assert "id" in log
        assert "user_id" in log
        assert log["user_id"] == str(user_id)
        assert "action" in log
        assert log["action"] == "document_download"
        assert "resource_type" in log
        assert log["resource_type"] == "document"
        assert "resource_id" in log
        assert log["resource_id"] == str(resource_id)
        assert "ip_address" in log
        assert log["ip_address"] == "10.0.0.1"
        assert "created_at" in log

    @pytest.mark.asyncio
    async def test_access_log_pagination_limit(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Pagination mit Limit funktioniert."""
        # Create 5 mock logs
        mock_logs = []
        for i in range(5):
            mock_log = MagicMock(spec=AuditLog)
            mock_log.id = uuid4()
            mock_log.user_id = uuid4()
            mock_log.action = "document_view"
            mock_log.resource_type = "document"
            mock_log.resource_id = uuid4()
            mock_log.ip_address = f"192.168.1.{i}"
            mock_log.created_at = datetime.now(timezone.utc) - timedelta(hours=i)
            mock_logs.append(mock_log)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs[:3]  # Limit 3
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_access_log(company_id, days=30, limit=3)

        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_access_log_pagination_offset(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Pagination mit Offset funktioniert."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "document_view"
        mock_log.resource_type = "document"
        mock_log.resource_id = uuid4()
        mock_log.ip_address = "192.168.1.5"
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_access_log(
            company_id, days=30, limit=10, offset=5
        )

        assert isinstance(logs, list)


# =============================================================================
# Export Log Tests
# =============================================================================


class TestGetExportLog:
    """Tests fuer get_export_log."""

    @pytest.mark.asyncio
    async def test_returns_export_log_list(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Gibt Liste von Export-Events zurueck."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "document_export"
        mock_log.resource_type = "document"
        mock_log.ip_address = "192.168.1.1"
        mock_log.audit_metadata = {"format": "pdf"}
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_export_log(company_id, days=30)

        assert isinstance(logs, list)
        assert len(logs) == 1
        assert logs[0]["action"] == "document_export"
        assert "metadata" in logs[0]

    @pytest.mark.asyncio
    async def test_export_log_metadata(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Export Log enthaelt Metadata."""
        metadata = {"format": "zip", "file_count": 10}
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "user_data_export"
        mock_log.resource_type = "user"
        mock_log.ip_address = "192.168.1.1"
        mock_log.audit_metadata = metadata
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_export_log(company_id, days=30)

        assert logs[0]["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_export_log_pagination(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Export Log Pagination."""
        mock_logs = []
        for i in range(3):
            mock_log = MagicMock(spec=AuditLog)
            mock_log.id = uuid4()
            mock_log.user_id = uuid4()
            mock_log.action = "document_export"
            mock_log.resource_type = "document"
            mock_log.ip_address = "192.168.1.1"
            mock_log.audit_metadata = {}
            mock_log.created_at = datetime.now(timezone.utc) - timedelta(hours=i)
            mock_logs.append(mock_log)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs[:2]
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_export_log(company_id, days=30, limit=2)

        assert len(logs) == 2


# =============================================================================
# Anomalies Tests
# =============================================================================


class TestGetAnomalies:
    """Tests fuer get_anomalies."""

    @pytest.mark.asyncio
    async def test_returns_anomalies_list(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Gibt Liste von Anomalien zurueck."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "login_failed"
        mock_log.error_message = "Invalid credentials"
        mock_log.ip_address = "192.168.1.1"
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        anomalies = await dashboard_service.get_anomalies(company_id, days=7)

        assert isinstance(anomalies, list)
        assert len(anomalies) == 1

    @pytest.mark.asyncio
    async def test_anomaly_severity_levels(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Anomalien haben unterschiedliche Severity-Level."""
        # Failed login = medium
        mock_log1 = MagicMock(spec=AuditLog)
        mock_log1.id = uuid4()
        mock_log1.user_id = uuid4()
        mock_log1.action = "login_failed"
        mock_log1.error_message = "Invalid credentials"
        mock_log1.ip_address = "192.168.1.1"
        mock_log1.created_at = datetime.now(timezone.utc)

        # Failed export = high
        mock_log2 = MagicMock(spec=AuditLog)
        mock_log2.id = uuid4()
        mock_log2.user_id = uuid4()
        mock_log2.action = "document_export_failed"
        mock_log2.error_message = "Permission denied"
        mock_log2.ip_address = "192.168.1.2"
        mock_log2.created_at = datetime.now(timezone.utc)

        # Failed admin action = critical
        mock_log3 = MagicMock(spec=AuditLog)
        mock_log3.id = uuid4()
        mock_log3.user_id = uuid4()
        mock_log3.action = "admin_delete_failed"
        mock_log3.error_message = "Access denied"
        mock_log3.ip_address = "192.168.1.3"
        mock_log3.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log1, mock_log2, mock_log3]
        mock_db.execute.return_value = mock_result

        anomalies = await dashboard_service.get_anomalies(company_id, days=7)

        assert len(anomalies) == 3
        severities = {a["severity"] for a in anomalies}
        assert "medium" in severities
        assert "high" in severities
        assert "critical" in severities

    @pytest.mark.asyncio
    async def test_anomaly_categorization(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Anomalien werden korrekt kategorisiert."""
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid4()
        mock_log.user_id = uuid4()
        mock_log.action = "login_failed"
        mock_log.error_message = "Invalid password"
        mock_log.ip_address = "192.168.1.1"
        mock_log.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        anomalies = await dashboard_service.get_anomalies(company_id, days=7)

        anomaly = anomalies[0]
        assert anomaly["type"] == "failed_login"
        assert anomaly["severity"] == "medium"
        assert "id" in anomaly
        assert "user_id" in anomaly
        assert "action" in anomaly
        assert "error_message" in anomaly
        assert "ip_address" in anomaly
        assert "created_at" in anomaly

    @pytest.mark.asyncio
    async def test_anomalies_limit(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Anomalien-Limit wird respektiert."""
        mock_logs = []
        for i in range(10):
            mock_log = MagicMock(spec=AuditLog)
            mock_log.id = uuid4()
            mock_log.user_id = uuid4()
            mock_log.action = "login_failed"
            mock_log.error_message = "Invalid credentials"
            mock_log.ip_address = f"192.168.1.{i}"
            mock_log.created_at = datetime.now(timezone.utc) - timedelta(hours=i)
            mock_logs.append(mock_log)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_logs[:5]
        mock_db.execute.return_value = mock_result

        anomalies = await dashboard_service.get_anomalies(company_id, days=7, limit=5)

        assert len(anomalies) == 5


# =============================================================================
# Compliance Score Calculation Tests
# =============================================================================


class TestComplianceScoreCalculation:
    """Tests fuer Compliance-Score Berechnung."""

    @pytest.mark.asyncio
    async def test_perfect_score_with_no_errors(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Perfekter Score (100) ohne Fehler."""
        # 1000 accesses, 0 anomalies, 0 errors
        query_results = [
            MagicMock(scalar=MagicMock(return_value=1000)),  # total_accesses
            MagicMock(scalar=MagicMock(return_value=0)),     # sensitive_accesses
            MagicMock(scalar=MagicMock(return_value=0)),     # export_count
            MagicMock(scalar=MagicMock(return_value=0)),     # anomaly_count
            MagicMock(scalar=MagicMock(return_value=0)),     # error_count
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        assert snapshot["metrics"]["compliance_score"] == 100.0

    @pytest.mark.asyncio
    async def test_score_decreases_with_anomalies(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Score sinkt mit steigenden Anomalien."""
        # 100 accesses, 10 anomalies (10% rate), 0 errors
        query_results = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=10)),  # 10% anomaly rate
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        score = snapshot["metrics"]["compliance_score"]
        assert score < 100.0
        # 10% anomaly rate -> -3 points (10% * 30)
        assert score == 97.0

    @pytest.mark.asyncio
    async def test_score_clamped_to_zero(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Score wird auf 0 begrenzt."""
        # Massive errors and anomalies exceeding total_accesses
        # Score = 100 - (anomaly_count/total)*30 - (error_count/total)*20
        # = 100 - (50/10)*30 - (50/10)*20 = 100 - 150 - 100 = -150 -> clamped to 0
        query_results = [
            MagicMock(scalar=MagicMock(return_value=10)),    # total_accesses
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=50)),    # anomaly_count >> total
            MagicMock(scalar=MagicMock(return_value=50)),    # error_count >> total
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        mock_db.execute.side_effect = query_results

        snapshot = await dashboard_service.get_dashboard_snapshot(company_id, days=30)

        score = snapshot["metrics"]["compliance_score"]
        assert score >= 0.0  # Never negative
        assert score == 0.0  # Should be clamped to 0


# =============================================================================
# Empty Results Tests
# =============================================================================


class TestEmptyResults:
    """Tests fuer leere Ergebnisse."""

    @pytest.mark.asyncio
    async def test_empty_access_log(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Leeres Access-Log."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_access_log(company_id, days=30)

        assert logs == []

    @pytest.mark.asyncio
    async def test_empty_export_log(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Leeres Export-Log."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        logs = await dashboard_service.get_export_log(company_id, days=30)

        assert logs == []

    @pytest.mark.asyncio
    async def test_empty_anomalies(
        self,
        dashboard_service,
        mock_db,
        company_id,
    ):
        """Test: Keine Anomalien."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        anomalies = await dashboard_service.get_anomalies(company_id, days=7)

        assert anomalies == []

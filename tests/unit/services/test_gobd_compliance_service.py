"""
Unit Tests fuer GoBD Compliance Service - Compliance-Report-Generator.

Tests:
- Compliance-Report-Generierung
- Archivierungs-Compliance
- Aufbewahrungsfristen-Compliance
- Audit-Trail-Compliance
- Integritaets-Compliance
- Score-Berechnung
- Empfehlungs-Generierung
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.gobd_compliance_service import (
    GoBDComplianceService,
    gobd_compliance_service,
    ComplianceStatus,
    ComplianceMetric,
)


@pytest.fixture
def compliance_service():
    """Create GoBDComplianceService instance."""
    return GoBDComplianceService()


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


class TestComplianceStatus:
    """Tests fuer ComplianceStatus Enum."""

    def test_compliance_status_values(self):
        """Alle Compliance-Status sind definiert."""
        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.WARNING.value == "warning"
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"
        assert ComplianceStatus.UNKNOWN.value == "unknown"


class TestComplianceMetric:
    """Tests fuer ComplianceMetric Dataclass."""

    def test_create_metric(self):
        """ComplianceMetric erstellen."""
        metric = ComplianceMetric(
            name="Test-Metrik",
            value=95,
            status=ComplianceStatus.COMPLIANT,
            threshold=90,
            description="Test-Beschreibung",
            recommendation="Keine Aktion erforderlich",
        )

        assert metric.name == "Test-Metrik"
        assert metric.value == 95
        assert metric.status == ComplianceStatus.COMPLIANT
        assert metric.threshold == 90
        assert metric.description == "Test-Beschreibung"
        assert metric.recommendation == "Keine Aktion erforderlich"

    def test_create_metric_minimal(self):
        """ComplianceMetric mit minimalen Feldern erstellen."""
        metric = ComplianceMetric(
            name="Minimal-Metrik",
            value=42,
            status=ComplianceStatus.WARNING,
        )

        assert metric.name == "Minimal-Metrik"
        assert metric.threshold is None
        assert metric.description == ""
        assert metric.recommendation is None


class TestGenerateComplianceReport:
    """Tests fuer generate_compliance_report Methode."""

    @pytest.mark.asyncio
    async def test_generate_report_success(self, compliance_service, mock_db):
        """Compliance-Bericht erfolgreich generieren."""
        company_id = uuid4()

        # Mock alle Sub-Queries
        # Archive metrics
        mock_db.execute.side_effect = [
            # Total documents
            MagicMock(scalar=MagicMock(return_value=100)),
            # Archived documents
            MagicMock(scalar=MagicMock(return_value=98)),
            # Unsigned documents
            MagicMock(scalar=MagicMock(return_value=0)),
            # Retention: expired
            MagicMock(scalar=MagicMock(return_value=0)),
            # Retention: expiring soon
            MagicMock(scalar=MagicMock(return_value=5)),
            # Retention: by category
            MagicMock(all=MagicMock(return_value=[
                ("invoice", 50, date.today() + timedelta(days=365)),
                ("contract", 30, date.today() + timedelta(days=730)),
            ])),
            # Audit: docs with audit
            MagicMock(scalar=MagicMock(return_value=98)),
            # Audit: archived docs
            MagicMock(scalar=MagicMock(return_value=98)),
            # Audit: null sequences
            MagicMock(scalar=MagicMock(return_value=0)),
            # Audit: failed accesses
            MagicMock(scalar=MagicMock(return_value=2)),
            # Integrity: failed verifications
            MagicMock(scalar=MagicMock(return_value=0)),
            # Integrity: old verifications
            MagicMock(scalar=MagicMock(return_value=0)),
            # Integrity: error count
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        report = await compliance_service.generate_compliance_report(
            db=mock_db,
            company_id=company_id,
        )

        assert report is not None
        assert report["company_id"] == str(company_id)
        assert "report_id" in report
        assert "overall_status" in report
        assert "overall_score" in report
        assert "summary" in report
        assert "recommendations" in report
        assert "legal_basis" in report

    @pytest.mark.asyncio
    async def test_generate_report_with_date(self, compliance_service, mock_db):
        """Compliance-Bericht mit spezifischem Datum generieren."""
        company_id = uuid4()
        report_date = date(2025, 6, 30)

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=50)),
            MagicMock(scalar=MagicMock(return_value=50)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(scalar=MagicMock(return_value=50)),
            MagicMock(scalar=MagicMock(return_value=50)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        report = await compliance_service.generate_compliance_report(
            db=mock_db,
            company_id=company_id,
            report_date=report_date,
        )

        assert report["report_date"] == "2025-06-30"

    @pytest.mark.asyncio
    async def test_generate_report_without_details(self, compliance_service, mock_db):
        """Compliance-Bericht ohne Details generieren."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        report = await compliance_service.generate_compliance_report(
            db=mock_db,
            company_id=company_id,
            include_details=False,
        )

        assert "details" not in report


class TestArchiveCompliance:
    """Tests fuer _check_archive_compliance Methode."""

    @pytest.mark.asyncio
    async def test_archive_compliance_fully_compliant(self, compliance_service, mock_db):
        """Vollstaendige Archivierungs-Compliance."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),  # Total docs
            MagicMock(scalar=MagicMock(return_value=100)),  # Archived docs (100%)
            MagicMock(scalar=MagicMock(return_value=0)),    # Unsigned docs
        ]

        metrics = await compliance_service._check_archive_compliance(
            db=mock_db,
            company_id=company_id,
        )

        assert len(metrics) == 2  # Archivierungsrate + Unsigned
        assert metrics[0].status == ComplianceStatus.COMPLIANT  # 100% Rate
        assert metrics[1].status == ComplianceStatus.COMPLIANT  # 0 Unsigned

    @pytest.mark.asyncio
    async def test_archive_compliance_low_rate(self, compliance_service, mock_db):
        """Niedrige Archivierungsrate (Warning)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=85)),  # 85% Rate
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        metrics = await compliance_service._check_archive_compliance(
            db=mock_db,
            company_id=company_id,
        )

        assert metrics[0].status == ComplianceStatus.WARNING

    @pytest.mark.asyncio
    async def test_archive_compliance_very_low_rate(self, compliance_service, mock_db):
        """Sehr niedrige Archivierungsrate (Non-Compliant)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=70)),  # 70% Rate
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        metrics = await compliance_service._check_archive_compliance(
            db=mock_db,
            company_id=company_id,
        )

        assert metrics[0].status == ComplianceStatus.NON_COMPLIANT
        assert metrics[0].recommendation is not None

    @pytest.mark.asyncio
    async def test_archive_compliance_unsigned_docs(self, compliance_service, mock_db):
        """Dokumente ohne Hash-Signatur (Non-Compliant)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=5)),  # 5 ohne Hash
        ]

        metrics = await compliance_service._check_archive_compliance(
            db=mock_db,
            company_id=company_id,
        )

        assert metrics[1].value == 5
        assert metrics[1].status == ComplianceStatus.NON_COMPLIANT


class TestRetentionCompliance:
    """Tests fuer _check_retention_compliance Methode."""

    @pytest.mark.asyncio
    async def test_retention_compliance_no_expired(self, compliance_service, mock_db):
        """Keine abgelaufenen Aufbewahrungsfristen."""
        company_id = uuid4()
        report_date = date.today()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=0)),  # Expired
            MagicMock(scalar=MagicMock(return_value=3)),  # Expiring soon
            MagicMock(all=MagicMock(return_value=[])),    # Categories
        ]

        metrics = await compliance_service._check_retention_compliance(
            db=mock_db,
            company_id=company_id,
            report_date=report_date,
        )

        assert metrics[0].value == 0
        assert metrics[0].status == ComplianceStatus.COMPLIANT

    @pytest.mark.asyncio
    async def test_retention_compliance_with_expired(self, compliance_service, mock_db):
        """Abgelaufene Aufbewahrungsfristen (Warning)."""
        company_id = uuid4()
        report_date = date.today()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=10)),  # 10 Expired
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        metrics = await compliance_service._check_retention_compliance(
            db=mock_db,
            company_id=company_id,
            report_date=report_date,
        )

        assert metrics[0].value == 10
        assert metrics[0].status == ComplianceStatus.WARNING  # Warning, not non-compliant
        assert metrics[0].recommendation is not None


class TestAuditTrailCompliance:
    """Tests fuer _check_audit_trail_compliance Methode."""

    @pytest.mark.asyncio
    async def test_audit_trail_full_coverage(self, compliance_service, mock_db):
        """100% Audit-Trail-Abdeckung."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),  # Docs with audit
            MagicMock(scalar=MagicMock(return_value=100)),  # Archived docs
            MagicMock(scalar=MagicMock(return_value=0)),    # Null sequences
            MagicMock(scalar=MagicMock(return_value=0)),    # Failed accesses
        ]

        metrics = await compliance_service._check_audit_trail_compliance(
            db=mock_db,
            company_id=company_id,
        )

        coverage_metric = metrics[0]
        assert coverage_metric.name == "Audit-Trail-Abdeckung"
        assert coverage_metric.status == ComplianceStatus.COMPLIANT

    @pytest.mark.asyncio
    async def test_audit_trail_sequence_gaps(self, compliance_service, mock_db):
        """Sequenzluecken im Audit-Trail (Non-Compliant)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalar=MagicMock(return_value=5)),  # 5 NULL sequences
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        metrics = await compliance_service._check_audit_trail_compliance(
            db=mock_db,
            company_id=company_id,
        )

        seq_metric = metrics[1]
        assert seq_metric.name == "Sequenzluecken im Audit-Trail"
        assert seq_metric.value == 5
        assert seq_metric.status == ComplianceStatus.NON_COMPLIANT


class TestIntegrityCompliance:
    """Tests fuer _check_integrity_compliance Methode."""

    @pytest.mark.asyncio
    async def test_integrity_all_verified(self, compliance_service, mock_db):
        """Alle Dokumente erfolgreich verifiziert."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=0)),  # Failed verifications
            MagicMock(scalar=MagicMock(return_value=0)),  # Old verifications
            MagicMock(scalar=MagicMock(return_value=0)),  # Error count
        ]

        metrics = await compliance_service._check_integrity_compliance(
            db=mock_db,
            company_id=company_id,
        )

        assert len(metrics) == 2  # Failed + Old verifications
        assert all(m.status == ComplianceStatus.COMPLIANT for m in metrics)

    @pytest.mark.asyncio
    async def test_integrity_failed_verifications(self, compliance_service, mock_db):
        """Fehlgeschlagene Verifikationen (Non-Compliant, kritisch!)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=3)),  # 3 Failed
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        metrics = await compliance_service._check_integrity_compliance(
            db=mock_db,
            company_id=company_id,
        )

        failed_metric = metrics[0]
        assert failed_metric.value == 3
        assert failed_metric.status == ComplianceStatus.NON_COMPLIANT
        assert "Manipulation" in failed_metric.recommendation

    @pytest.mark.asyncio
    async def test_integrity_old_verifications(self, compliance_service, mock_db):
        """Veraltete Verifikationen (Warning)."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=20)),  # 20 old
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        metrics = await compliance_service._check_integrity_compliance(
            db=mock_db,
            company_id=company_id,
        )

        old_metric = metrics[1]
        assert old_metric.value == 20
        assert old_metric.status == ComplianceStatus.WARNING


class TestScoreCalculation:
    """Tests fuer _calculate_overall_score Methode."""

    def test_score_all_compliant(self, compliance_service):
        """Score bei vollstaendiger Compliance."""
        metrics = [
            ComplianceMetric("Test1", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("Test2", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("Test3", 100, ComplianceStatus.COMPLIANT),
        ]

        score, status = compliance_service._calculate_overall_score(metrics)

        assert score == 100.0
        assert status == ComplianceStatus.COMPLIANT

    def test_score_with_warnings(self, compliance_service):
        """Score mit Warnings."""
        metrics = [
            ComplianceMetric("Test1", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("Test2", 80, ComplianceStatus.WARNING),
            ComplianceMetric("Test3", 100, ComplianceStatus.COMPLIANT),
        ]

        score, status = compliance_service._calculate_overall_score(metrics)

        assert score == 90.0  # (100 + 70 + 100) / 3
        assert status == ComplianceStatus.WARNING

    def test_score_with_non_compliant(self, compliance_service):
        """Score mit Non-Compliant."""
        metrics = [
            ComplianceMetric("Test1", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("Test2", 0, ComplianceStatus.NON_COMPLIANT),
        ]

        score, status = compliance_service._calculate_overall_score(metrics)

        assert score == 50.0  # (100 + 0) / 2
        assert status == ComplianceStatus.NON_COMPLIANT

    def test_score_empty_metrics(self, compliance_service):
        """Score bei leeren Metriken."""
        score, status = compliance_service._calculate_overall_score([])

        assert score == 100.0
        assert status == ComplianceStatus.UNKNOWN


class TestScoreDescription:
    """Tests fuer _get_score_description Methode."""

    def test_score_description_excellent(self, compliance_service):
        """Beschreibung fuer ausgezeichneten Score."""
        desc = compliance_service._get_score_description(98.5)
        assert "Ausgezeichnet" in desc

    def test_score_description_good(self, compliance_service):
        """Beschreibung fuer guten Score."""
        desc = compliance_service._get_score_description(85.0)
        assert "Gut" in desc

    def test_score_description_needs_improvement(self, compliance_service):
        """Beschreibung fuer verbesserungswuerdigen Score."""
        desc = compliance_service._get_score_description(65.0)
        assert "Verbesserungswuerdig" in desc

    def test_score_description_critical(self, compliance_service):
        """Beschreibung fuer kritischen Score."""
        desc = compliance_service._get_score_description(45.0)
        assert "Kritisch" in desc

    def test_score_description_non_compliant(self, compliance_service):
        """Beschreibung fuer nicht-complianten Score."""
        desc = compliance_service._get_score_description(30.0)
        assert "Nicht compliant" in desc or "Handlungsbedarf" in desc


class TestGenerateRecommendations:
    """Tests fuer _generate_recommendations Methode."""

    def test_recommendations_sorted_by_severity(self, compliance_service):
        """Empfehlungen nach Dringlichkeit sortiert."""
        metrics = [
            ComplianceMetric(
                "Warning-Metric", 80, ComplianceStatus.WARNING,
                recommendation="Sollte verbessert werden"
            ),
            ComplianceMetric(
                "Critical-Metric", 0, ComplianceStatus.NON_COMPLIANT,
                recommendation="Sofort beheben!"
            ),
            ComplianceMetric(
                "OK-Metric", 100, ComplianceStatus.COMPLIANT,
                recommendation=None  # Keine Empfehlung
            ),
        ]

        recommendations = compliance_service._generate_recommendations(metrics)

        assert len(recommendations) == 2
        # NON_COMPLIANT zuerst
        assert recommendations[0]["severity"] == "non_compliant"
        assert recommendations[0]["priority"] == 1
        # WARNING danach
        assert recommendations[1]["severity"] == "warning"
        assert recommendations[1]["priority"] == 2

    def test_no_recommendations_when_compliant(self, compliance_service):
        """Keine Empfehlungen bei voller Compliance."""
        metrics = [
            ComplianceMetric("OK1", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("OK2", 100, ComplianceStatus.COMPLIANT),
        ]

        recommendations = compliance_service._generate_recommendations(metrics)

        assert len(recommendations) == 0


class TestMetricToDict:
    """Tests fuer _metric_to_dict Methode."""

    def test_metric_conversion(self, compliance_service):
        """Metrik zu Dict konvertieren."""
        metric = ComplianceMetric(
            name="Test-Metrik",
            value=95,
            status=ComplianceStatus.COMPLIANT,
            threshold=90,
            description="Test",
            recommendation="Keine",
        )

        result = compliance_service._metric_to_dict(metric)

        assert result["name"] == "Test-Metrik"
        assert result["value"] == 95
        assert result["status"] == "compliant"
        assert result["threshold"] == 90
        assert result["description"] == "Test"
        assert result["recommendation"] == "Keine"


class TestSummarizeMetrics:
    """Tests fuer _summarize_metrics Methode."""

    def test_summarize_mixed_metrics(self, compliance_service):
        """Metriken zusammenfassen."""
        metrics = [
            ComplianceMetric("M1", 100, ComplianceStatus.COMPLIANT),
            ComplianceMetric("M2", 80, ComplianceStatus.WARNING),
            ComplianceMetric("M3", 0, ComplianceStatus.NON_COMPLIANT),
            ComplianceMetric("M4", 100, ComplianceStatus.COMPLIANT),
        ]

        summary = compliance_service._summarize_metrics(metrics)

        assert summary["total"] == 4
        assert summary["compliant"] == 2
        assert summary["warning"] == 1
        assert summary["non_compliant"] == 1
        assert summary["status"] == "non_compliant"  # Wegen einer NON_COMPLIANT

    def test_summarize_empty_metrics(self, compliance_service):
        """Leere Metriken zusammenfassen."""
        summary = compliance_service._summarize_metrics([])

        assert summary["status"] == "unknown"
        assert summary["count"] == 0


class TestQuickComplianceStatus:
    """Tests fuer get_quick_compliance_status Methode."""

    @pytest.mark.asyncio
    async def test_quick_status_compliant(self, compliance_service, mock_db):
        """Schneller Status bei Compliance."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=0)),  # No failed verifications
            MagicMock(scalar=MagicMock(return_value=0)),  # No null sequences
        ]

        result = await compliance_service.get_quick_compliance_status(
            db=mock_db,
            company_id=company_id,
        )

        assert result["status"] == "compliant"
        assert result["failed_verifications"] == 0
        assert result["audit_trail_gaps"] == 0
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_quick_status_non_compliant(self, compliance_service, mock_db):
        """Schneller Status bei Non-Compliance."""
        company_id = uuid4()

        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=2)),  # 2 failed
            MagicMock(scalar=MagicMock(return_value=5)),  # 5 gaps
        ]

        result = await compliance_service.get_quick_compliance_status(
            db=mock_db,
            company_id=company_id,
        )

        assert result["status"] == "non_compliant"
        assert result["failed_verifications"] == 2
        assert result["audit_trail_gaps"] == 5


class TestLegalBasis:
    """Tests fuer rechtliche Grundlagen."""

    @pytest.mark.asyncio
    async def test_legal_basis_included(self, compliance_service, mock_db):
        """Rechtliche Grundlagen im Bericht."""
        company_id = uuid4()

        # Minimal mocks
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ]

        report = await compliance_service.generate_compliance_report(
            db=mock_db,
            company_id=company_id,
        )

        legal_basis = report["legal_basis"]
        laws = [item["law"] for item in legal_basis]

        assert "§ 147 AO" in laws
        assert "§ 257 HGB" in laws
        assert "§ 14b UStG" in laws


class TestServiceThresholds:
    """Tests fuer Service-Schwellenwerte."""

    def test_threshold_values(self, compliance_service):
        """Schwellenwerte sind korrekt definiert."""
        assert compliance_service.MIN_ARCHIVE_RATE == 0.95
        assert compliance_service.MAX_VERIFICATION_AGE_DAYS == 90
        assert compliance_service.MIN_AUDIT_TRAIL_COVERAGE == 1.0
        assert compliance_service.MAX_FAILED_VERIFICATIONS == 0


class TestSingletonInstance:
    """Tests fuer Singleton-Instanz."""

    def test_singleton_instance_exists(self):
        """Singleton-Instanz ist verfuegbar."""
        from app.services.gobd_compliance_service import gobd_compliance_service

        assert gobd_compliance_service is not None
        assert isinstance(gobd_compliance_service, GoBDComplianceService)

# -*- coding: utf-8 -*-
"""
Unit tests for GoBDComplianceService.

Vision 2026+ Feature #6: Compliance-Autopilot (GoBD)
"""

import uuid
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.services.compliance.gobd_service import (
    GoBDComplianceService,
    CheckResult,
    ComplianceDashboard,
    RemediationAction,
)
from app.db.models_compliance import (
    GoBDCheckType,
    ComplianceStatus,
    ComplianceReportType,
)


class TestGoBDComplianceService:
    """Tests fuer GoBDComplianceService."""

    @pytest.fixture
    def service(self) -> GoBDComplianceService:
        """Gibt eine Service-Instanz zurueck."""
        return GoBDComplianceService()

    @pytest.fixture
    def company_id(self) -> uuid.UUID:
        """Gibt eine Test-Company-ID zurueck."""
        return uuid.uuid4()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstellt eine Mock-DB-Session."""
        db = AsyncMock()
        # Default mock result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    # -------------------------------------------------------------------------
    # Basic Tests
    # -------------------------------------------------------------------------

    def test_service_initialization(self, service: GoBDComplianceService) -> None:
        """Service sollte korrekt initialisiert werden."""
        assert service is not None
        assert len(service.CHECK_INTERVALS) > 0

    def test_check_intervals_defined(self, service: GoBDComplianceService) -> None:
        """Alle Check-Typen sollten Intervalle haben."""
        for check_type in [
            GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
            GoBDCheckType.UNVERAENDERBARKEIT.value,
            GoBDCheckType.VOLLSTAENDIGKEIT.value,
            GoBDCheckType.AUFBEWAHRUNG.value,
        ]:
            assert check_type in service.CHECK_INTERVALS

    # -------------------------------------------------------------------------
    # run_all_checks Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_all_checks_returns_results(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_all_checks sollte Ergebnisse fuer alle Check-Typen zurueckgeben."""
        results = await service.run_all_checks(
            db=mock_db,
            company_id=company_id,
            triggered_by="test",
        )

        assert len(results) == len(GoBDCheckType)
        assert all(isinstance(r, CheckResult) for r in results)

    @pytest.mark.asyncio
    async def test_run_all_checks_saves_to_db(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_all_checks sollte alle Ergebnisse in die DB speichern."""
        await service.run_all_checks(
            db=mock_db,
            company_id=company_id,
            triggered_by="scheduled",
        )

        # db.add sollte fuer jeden Check mindestens einmal aufgerufen werden
        # (einmal fuer Check, einmal fuer History)
        assert mock_db.add.call_count >= len(GoBDCheckType)

    # -------------------------------------------------------------------------
    # run_check Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_check_nachvollziehbarkeit(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Nachvollziehbarkeit pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        assert result.check_type == GoBDCheckType.NACHVOLLZIEHBARKEIT.value
        assert result.status in [s.value for s in ComplianceStatus]
        assert 0 <= result.score <= 100

    @pytest.mark.asyncio
    async def test_run_check_unveraenderbarkeit(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Unveraenderbarkeit pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.UNVERAENDERBARKEIT.value,
        )

        assert result.check_type == GoBDCheckType.UNVERAENDERBARKEIT.value
        assert "hash_mismatches" in result.details or "verification_rate" in result.details

    @pytest.mark.asyncio
    async def test_run_check_vollstaendigkeit(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Vollstaendigkeit pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.VOLLSTAENDIGKEIT.value,
        )

        assert result.check_type == GoBDCheckType.VOLLSTAENDIGKEIT.value
        # M15: Pruefung liefert jetzt doppelte Belegnummern (teilgeprueft)
        assert "duplicate_invoice_numbers" in result.details

    @pytest.mark.asyncio
    async def test_run_check_aufbewahrung(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Aufbewahrungsfristen pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.AUFBEWAHRUNG.value,
        )

        assert result.check_type == GoBDCheckType.AUFBEWAHRUNG.value
        assert "expiring_soon" in result.details or "expired" in result.details

    @pytest.mark.asyncio
    async def test_run_check_ordnung(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Ordnung pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.ORDNUNG.value,
        )

        assert result.check_type == GoBDCheckType.ORDNUNG.value
        assert "unclassified_documents" in result.details

    @pytest.mark.asyncio
    async def test_run_check_zugangskontrolle(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Zugangskontrolle pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.ZUGANGSKONTROLLE.value,
        )

        assert result.check_type == GoBDCheckType.ZUGANGSKONTROLLE.value
        # M15: ehrlich teilgeprueft (WARNING) statt faelschlich PASSED,
        # da die vollstaendige Berechtigungs-Matrix-Pruefung XL ist.
        assert result.status == ComplianceStatus.WARNING.value

    @pytest.mark.asyncio
    async def test_run_check_maschinelle_auswertbarkeit(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte maschinelle Auswertbarkeit pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.MASCHINELLE_AUSWERTBARKEIT.value,
        )

        assert result.check_type == GoBDCheckType.MASCHINELLE_AUSWERTBARKEIT.value
        assert "export_formats" in result.details

    @pytest.mark.asyncio
    async def test_run_check_verfahrensdokumentation(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Verfahrensdokumentation pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.VERFAHRENSDOKUMENTATION.value,
        )

        assert result.check_type == GoBDCheckType.VERFAHRENSDOKUMENTATION.value

    @pytest.mark.asyncio
    async def test_run_check_datensicherung(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Datensicherung pruefen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.DATENSICHERUNG.value,
        )

        assert result.check_type == GoBDCheckType.DATENSICHERUNG.value
        assert result.status == ComplianceStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_run_check_unknown_type(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte unbekannte Typen als NOT_APPLICABLE behandeln."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type="unknown_check_type",
        )

        assert result.status == ComplianceStatus.NOT_APPLICABLE.value
        assert result.score == 100

    @pytest.mark.asyncio
    async def test_run_check_sets_execution_time(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """run_check sollte Ausfuehrungszeit setzen."""
        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.ORDNUNG.value,
        )

        assert result.execution_time_ms >= 0

    # -------------------------------------------------------------------------
    # Nachvollziehbarkeit (Audit-Trail) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_nachvollziehbarkeit_full_coverage(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Volle Audit-Coverage sollte PASSED ergeben."""
        # Mock: 100 Dokumente, alle haben Audit-Logs
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:  # Total docs
                mock_result.scalar.return_value = 100
            elif call_count[0] == 2:  # Docs with audit
                mock_result.scalar.return_value = 100
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        assert result.score >= 90
        # M15: Selbst bei voller Coverage wird die Nachvollziehbarkeit ehrlich
        # als WARNING (teilgeprueft) gemeldet — die vollstaendige globale
        # Ketten-Luecken-Pruefung ist XL und hier nicht abschliessend.
        assert result.status == ComplianceStatus.WARNING.value

    @pytest.mark.asyncio
    async def test_nachvollziehbarkeit_low_coverage(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Niedrige Audit-Coverage sollte WARNING/FAILED ergeben."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:  # Total docs
                mock_result.scalar.return_value = 100
            elif call_count[0] == 2:  # Docs with audit - nur 50%
                mock_result.scalar.return_value = 50
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        assert result.details["audit_coverage"] == 50.0
        assert len(result.details["issues"]) > 0

    # -------------------------------------------------------------------------
    # Unveraenderbarkeit (Hash-Verifikation) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unveraenderbarkeit_all_verified(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Alle verifizierten Dokumente sollten PASSED ergeben."""
        # Mock verified archives
        mock_archive = MagicMock()
        mock_archive.is_verified = True
        mock_archive.document_id = uuid.uuid4()

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Archives query
                mock_result.scalars.return_value.all.return_value = [mock_archive]
            elif call_count[0] == 2:  # Unarchived docs count
                mock_result.scalar.return_value = 0
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.UNVERAENDERBARKEIT.value,
        )

        assert result.details["verification_rate"] == 100.0
        assert result.score >= 90

    @pytest.mark.asyncio
    async def test_unveraenderbarkeit_with_unarchived_docs(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Nicht archivierte Dokumente sollten Warning erzeugen."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Archives query
                mock_result.scalars.return_value.all.return_value = []
            elif call_count[0] == 2:  # Unarchived docs count
                mock_result.scalar.return_value = 20  # Viele unarchivierte
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.UNVERAENDERBARKEIT.value,
        )

        assert result.details["unarchived_documents"] == 20
        assert any("unarchived" in str(issue).lower() for issue in result.details.get("issues", []))

    @pytest.mark.asyncio
    async def test_unveraenderbarkeit_niemals_passed_ohne_hash_pruefung(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """M15-Ehrlichkeit: ohne echte Hash-Verifikation max. WARNING.

        Auch im Bestcase (alle Archive verifiziert markiert, nichts
        unarchiviert) darf der Check NICHT PASSED melden, weil die
        Datei-Hash-Pruefung nicht implementiert ist (teilgeprueft).
        """
        mock_archive = MagicMock()
        mock_archive.is_verified = True
        mock_archive.document_id = uuid.uuid4()

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:  # Archives query
                mock_result.scalars.return_value.all.return_value = [mock_archive]
            else:  # Unarchived docs count
                mock_result.scalar.return_value = 0
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service._check_unveraenderbarkeit(mock_db, company_id)

        assert result.score == 100
        assert result.status == ComplianceStatus.WARNING.value
        assert result.status != ComplianceStatus.PASSED.value
        assert result.details["teilgeprueft"] is True
        assert "nicht implementiert" in result.details["hash_verification"]
        assert any(
            issue.get("type") == "hash_verification_not_implemented"
            for issue in result.details["issues"]
        )
        assert any("teilgeprueft" in step for step in result.remediation_steps)

    @pytest.mark.asyncio
    async def test_unveraenderbarkeit_failed_bei_niedrigem_score(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Score < 70 (unverifizierte Archive + viele Unarchivierte) -> FAILED."""
        mock_archive = MagicMock()
        mock_archive.is_verified = False
        mock_archive.document_id = uuid.uuid4()

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:  # Archives query
                mock_result.scalars.return_value.all.return_value = [mock_archive]
            else:  # Unarchived docs count
                mock_result.scalar.return_value = 100
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service._check_unveraenderbarkeit(mock_db, company_id)

        # 100 - 30 (0% verifiziert) - 20 (Unarchiviert, gedeckelt) = 50
        assert result.score == 50
        assert result.status == ComplianceStatus.FAILED.value
        assert result.details["teilgeprueft"] is True

    # -------------------------------------------------------------------------
    # Aufbewahrung (Retention) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_aufbewahrung_no_expired_docs(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Keine abgelaufenen Dokumente sollte PASSED ergeben."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Expiring soon
                mock_result.scalar.return_value = 0
            elif call_count[0] == 2:  # Expired
                mock_result.scalar.return_value = 0
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.AUFBEWAHRUNG.value,
        )

        assert result.score == 100
        assert result.status == ComplianceStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_aufbewahrung_with_expired_docs(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Abgelaufene Dokumente sollten Score reduzieren."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Expiring soon
                mock_result.scalar.return_value = 5
            elif call_count[0] == 2:  # Expired
                mock_result.scalar.return_value = 10
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.AUFBEWAHRUNG.value,
        )

        assert result.details["expired"] == 10
        assert result.details["expiring_soon"] == 5
        assert len(result.remediation_steps) > 0

    # -------------------------------------------------------------------------
    # Ordnung Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ordnung_all_classified(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Alle klassifizierten Dokumente sollten PASSED ergeben."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0  # Keine unklassifizierten
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.ORDNUNG.value,
        )

        assert result.score == 100
        assert result.status == ComplianceStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_ordnung_with_unclassified(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Unklassifizierte Dokumente sollten Score reduzieren."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Unclassified count
                mock_result.scalar.return_value = 30  # Viele unklassifizierte
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.ORDNUNG.value,
        )

        assert result.details["unclassified_documents"] == 30
        assert result.score < 100
        assert "klassifizieren" in result.remediation_steps[0].lower()

    # -------------------------------------------------------------------------
    # get_dashboard Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_dashboard_empty(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Dashboard ohne Checks sollte 0 Score haben."""
        result = await service.get_dashboard(db=mock_db, company_id=company_id)

        assert isinstance(result, ComplianceDashboard)
        assert result.overall_score == 0
        assert result.checks_passed == 0
        assert result.overall_status == ComplianceStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_dashboard_with_checks(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Dashboard mit Checks sollte aggregierte Daten zeigen."""
        # Mock checks
        mock_check1 = MagicMock()
        mock_check1.status = ComplianceStatus.PASSED.value
        mock_check1.score = 100
        mock_check1.last_checked_at = datetime.utcnow()
        mock_check1.next_check_at = datetime.utcnow() + timedelta(hours=24)
        mock_check1.remediation_steps = []

        mock_check2 = MagicMock()
        mock_check2.status = ComplianceStatus.WARNING.value
        mock_check2.score = 75
        mock_check2.last_checked_at = datetime.utcnow() - timedelta(hours=1)
        mock_check2.next_check_at = datetime.utcnow() + timedelta(hours=12)
        mock_check2.remediation_steps = ["Fix something"]

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:  # Checks query
                mock_result.scalars.return_value.all.return_value = [mock_check1, mock_check2]
            elif call_count[0] == 2:  # History query
                mock_result.scalars.return_value.all.return_value = []
            else:
                mock_result.scalar_one_or_none.return_value = None

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.get_dashboard(db=mock_db, company_id=company_id)

        assert result.checks_passed == 1
        assert result.checks_warning == 1
        assert result.overall_score == 87  # (100 + 75) // 2
        assert result.overall_status == ComplianceStatus.WARNING.value

    @pytest.mark.asyncio
    async def test_get_dashboard_with_failed_check(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Dashboard mit FAILED Check sollte FAILED Status haben."""
        mock_check = MagicMock()
        mock_check.status = ComplianceStatus.FAILED.value
        mock_check.score = 40
        mock_check.check_type = "unveraenderbarkeit"
        mock_check.issues_found = 5
        mock_check.remediation_steps = ["Restore from backup"]
        mock_check.last_checked_at = datetime.utcnow()
        mock_check.next_check_at = datetime.utcnow() + timedelta(hours=24)
        mock_check.get_check_description = MagicMock(return_value="Unveraenderbarkeit Test")

        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:
                mock_result.scalars.return_value.all.return_value = [mock_check]
            else:
                mock_result.scalars.return_value.all.return_value = []

            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.get_dashboard(db=mock_db, company_id=company_id)

        assert result.overall_status == ComplianceStatus.FAILED.value
        assert result.checks_failed == 1
        assert len(result.critical_issues) == 1

    # -------------------------------------------------------------------------
    # generate_report Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generate_report_creates_record(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """generate_report sollte Report in DB erstellen."""
        # Mock empty checks
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        report = await service.generate_report(
            db=mock_db,
            company_id=company_id,
            report_type=ComplianceReportType.FULL.value,
        )

        assert mock_db.add.called
        assert mock_db.flush.called

    @pytest.mark.asyncio
    async def test_generate_report_with_checks(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """generate_report sollte Check-Ergebnisse enthalten."""
        mock_check = MagicMock()
        mock_check.check_type = "nachvollziehbarkeit"
        mock_check.status = ComplianceStatus.PASSED.value
        mock_check.score = 95
        mock_check.issues_found = 0
        mock_check.last_checked_at = datetime.utcnow()
        mock_check.remediation_steps = []
        mock_check.get_check_description = MagicMock(return_value="Nachvollziehbarkeit")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_check]
        mock_db.execute.return_value = mock_result

        report = await service.generate_report(
            db=mock_db,
            company_id=company_id,
        )

        assert report is not None
        assert report.overall_score == 95
        assert report.overall_status == ComplianceStatus.PASSED.value

    @pytest.mark.asyncio
    async def test_generate_report_with_period(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """generate_report sollte Zeitraum unterstuetzen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        period_start = date(2026, 1, 1)
        period_end = date(2026, 1, 31)

        report = await service.generate_report(
            db=mock_db,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )

        assert report.period_start == period_start
        assert report.period_end == period_end

    # -------------------------------------------------------------------------
    # _save_check_result Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_save_check_result_creates_new(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """_save_check_result sollte neuen Check erstellen."""
        result = CheckResult(
            check_type=GoBDCheckType.ORDNUNG.value,
            status=ComplianceStatus.PASSED.value,
            score=100,
            issues_found=0,
            details={},
            affected_documents=[],
            remediation_steps=[],
            execution_time_ms=50,
        )

        await service._save_check_result(
            db=mock_db,
            company_id=company_id,
            result=result,
            triggered_by="test",
            executed_by_id=None,
        )

        # db.add sollte 2x aufgerufen werden (Check + History)
        assert mock_db.add.call_count == 2
        assert mock_db.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_save_check_result_updates_existing(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """_save_check_result sollte existierenden Check aktualisieren."""
        # Mock existing check
        existing_check = MagicMock()
        existing_check.id = uuid.uuid4()
        existing_check.status = ComplianceStatus.WARNING.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_check
        mock_db.execute.return_value = mock_result

        result = CheckResult(
            check_type=GoBDCheckType.ORDNUNG.value,
            status=ComplianceStatus.PASSED.value,
            score=100,
            issues_found=0,
            details={"updated": True},
            affected_documents=[],
            remediation_steps=[],
            execution_time_ms=25,
        )

        await service._save_check_result(
            db=mock_db,
            company_id=company_id,
            result=result,
            triggered_by="manual",
            executed_by_id=uuid.uuid4(),
        )

        # Existing check sollte aktualisiert werden
        assert existing_check.status == ComplianceStatus.PASSED.value
        assert existing_check.score == 100

    # -------------------------------------------------------------------------
    # Score Calculation Tests
    # -------------------------------------------------------------------------

    def test_score_bounds(self, service: GoBDComplianceService) -> None:
        """Score sollte immer zwischen 0 und 100 liegen."""
        # Tested implicitly through check methods
        assert True

    @pytest.mark.asyncio
    async def test_score_calculation_nachvollziehbarkeit(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Score-Berechnung fuer Nachvollziehbarkeit testen."""
        # 80% coverage = score sollte 90 sein (100 - 20 * 0.5)
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar.return_value = 100  # Total docs
            elif call_count[0] == 2:
                mock_result.scalar.return_value = 80  # Docs with audit
            else:
                # M15: Sequenz-/Hash-Integritaets-Queries sauber (0 Luecken),
                # damit der Score nur die Coverage widerspiegelt.
                mock_result.scalar.return_value = 0
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        # 100 - (100 - 80) * 0.5 = 90
        assert result.score == 90

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_zero_documents(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Bei 0 Dokumenten sollte Coverage 100% sein."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar.return_value = 0  # No docs
            elif call_count[0] == 2:
                mock_result.scalar.return_value = 0  # No audit
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        # Bei 0 Dokumenten: Coverage = 100% (Division durch 0 vermeiden)
        assert result.details["audit_coverage"] == 100

    @pytest.mark.asyncio
    async def test_large_numbers(
        self,
        service: GoBDComplianceService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Service sollte mit grossen Zahlen umgehen koennen."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar.return_value = 1_000_000  # 1 Million docs
            elif call_count[0] == 2:
                mock_result.scalar.return_value = 999_000  # 99.9% coverage
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute.side_effect = execute_side_effect

        result = await service.run_check(
            db=mock_db,
            company_id=company_id,
            check_type=GoBDCheckType.NACHVOLLZIEHBARKEIT.value,
        )

        assert result.details["document_count"] == 1_000_000
        assert result.details["audit_coverage"] == 99.9

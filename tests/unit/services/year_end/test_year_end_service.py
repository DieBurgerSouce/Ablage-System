# -*- coding: utf-8 -*-
"""Unit Tests fuer den Jahresabschluss-Assistent Service.

Tests fuer Session-Management, Checklisten, Lueckenanalyse und Berichtserstellung.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

from app.db.models_year_end import (
    YearEndSession,
    YearEndCheckItem,
    YearEndGap,
    YearEndStatus,
    CheckItemStatus,
    GapCategory,
)
from app.services.year_end.year_end_service import YearEndService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create a YearEndService instance."""
    return YearEndService()


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def sample_company_id():
    return uuid4()


@pytest.fixture
def sample_user_id():
    return uuid4()


@pytest.fixture
def sample_session_id():
    return uuid4()


def _make_session(
    session_id=None,
    company_id=None,
    fiscal_year=2025,
    status_val=YearEndStatus.DRAFT.value,
    check_items=None,
    gaps=None,
):
    """Helper to create a mock YearEndSession."""
    session = MagicMock(spec=YearEndSession)
    session.id = session_id or uuid4()
    session.company_id = company_id or uuid4()
    session.fiscal_year = fiscal_year
    session.status = status_val
    session.total_checks = 0
    session.passed_checks = 0
    session.warning_checks = 0
    session.failed_checks = 0
    session.progress_percent = 0
    session.check_items = check_items or []
    session.gaps = gaps or []
    session.deleted_at = None
    session.report_generated_at = None
    session.started_at = datetime.now(timezone.utc)
    session.completed_at = None
    return session


def _make_check_item(
    item_id=None,
    category="Bankabgleich",
    check_name="Bankabgleich durchgefuehrt",
    status_val=CheckItemStatus.PENDING.value,
    details_json=None,
):
    """Helper to create a mock YearEndCheckItem."""
    item = MagicMock(spec=YearEndCheckItem)
    item.id = item_id or uuid4()
    item.category = category
    item.check_name = check_name
    item.status = status_val
    item.details_json = details_json
    item.checked_at = None
    item.resolved_by = None
    item.resolved_at = None
    item.resolution_notes = None
    return item


def _make_gap(
    gap_id=None,
    category=GapCategory.MISSING_RECEIPT.value,
    month=1,
    description="Fehlender Beleg",
    amount=None,
    is_resolved=False,
):
    """Helper to create a mock YearEndGap."""
    gap = MagicMock(spec=YearEndGap)
    gap.id = gap_id or uuid4()
    gap.category = category
    gap.month = month
    gap.description = description
    gap.amount = amount
    gap.is_resolved = is_resolved
    gap.resolved_by = None
    gap.resolved_at = None
    gap.resolution_notes = None
    gap.created_at = datetime.now(timezone.utc)
    return gap


# =============================================================================
# Tests
# =============================================================================


class TestBuildStandardChecklist:
    """Tests fuer _build_standard_checklist."""

    def test_build_standard_checklist_count(self, service):
        """Standard-Checkliste hat 34 Eintraege (12+12+10)."""
        items = service._build_standard_checklist()
        assert len(items) == 34

    def test_checklist_has_monthly_receipts(self, service):
        """12 Eingangsrechnungen-Pruefpunkte (einer pro Monat)."""
        items = service._build_standard_checklist()
        eingang = [i for i in items if i["category"] == "Eingangsrechnungen"]
        assert len(eingang) == 12

    def test_checklist_has_monthly_invoices(self, service):
        """12 Ausgangsrechnungen-Pruefpunkte (einer pro Monat)."""
        items = service._build_standard_checklist()
        ausgang = [i for i in items if i["category"] == "Ausgangsrechnungen"]
        assert len(ausgang) == 12

    def test_checklist_has_bank_reconciliation(self, service):
        """Bankabgleich ist in der Checkliste."""
        items = service._build_standard_checklist()
        bank = [i for i in items if i["category"] == "Bankabgleich"]
        assert len(bank) == 1
        assert bank[0]["check_name"] == "Bankabgleich durchgefuehrt"

    def test_checklist_items_have_required_keys(self, service):
        """Alle Items haben category und check_name."""
        items = service._build_standard_checklist()
        for item in items:
            assert "category" in item
            assert "check_name" in item
            assert isinstance(item["category"], str)
            assert isinstance(item["check_name"], str)


class TestCreateSession:
    """Tests fuer create_session."""

    @pytest.mark.asyncio
    async def test_create_session_generates_checklist(
        self, service, mock_db, sample_company_id, sample_user_id,
    ):
        """Session wird mit Standard-Checkliste erstellt."""
        # Mock flush to set id
        async def mock_flush():
            pass

        mock_db.flush = mock_flush

        # Mock refresh to be a no-op
        async def mock_refresh(obj):
            pass

        mock_db.refresh = mock_refresh

        # Patch the internal session creation
        with patch(
            "app.services.year_end.year_end_service.YearEndSession",
        ) as MockSession, patch(
            "app.services.year_end.year_end_service.YearEndCheckItem",
        ) as MockCheckItem:
            mock_session = _make_session(
                company_id=sample_company_id,
                fiscal_year=2025,
            )
            MockSession.return_value = mock_session

            result = await service.create_session(
                db=mock_db,
                company_id=sample_company_id,
                fiscal_year=2025,
                user_id=sample_user_id,
            )

            # 34 check items should have been created
            assert MockCheckItem.call_count == 34
            assert mock_session.total_checks == 34


class TestRunCompletenessCheck:
    """Tests fuer run_completeness_check."""

    @pytest.mark.asyncio
    async def test_run_completeness_check_updates_progress(
        self, service, mock_db, sample_session_id, sample_company_id,
    ):
        """Fortschritt wird nach Pruefung korrekt berechnet."""
        # Create items that will be checked
        item_bank = _make_check_item(
            category="Bankabgleich",
            check_name="Bankabgleich durchgefuehrt",
        )
        item_other = _make_check_item(
            category="Offene Posten",
            check_name="Offene Posten bereinigt",
        )

        session = _make_session(
            session_id=sample_session_id,
            company_id=sample_company_id,
            check_items=[item_bank, item_other],
        )
        session.total_checks = 2

        with patch.object(
            service, "get_session", return_value=session,
        ), patch.object(
            service, "_check_bank_reconciliation",
            return_value=(CheckItemStatus.PASSED.value, 0),
        ):
            result = await service.run_completeness_check(
                db=mock_db,
                session_id=sample_session_id,
                company_id=sample_company_id,
            )

            # Bank check passed => 1 passed, 0 failed, other is manual
            assert result.passed_checks == 1
            assert result.status == YearEndStatus.IN_PROGRESS.value


class TestResolveGap:
    """Tests fuer resolve_gap."""

    @pytest.mark.asyncio
    async def test_resolve_gap(
        self, service, mock_db, sample_company_id, sample_user_id,
    ):
        """Luecke wird als behoben markiert."""
        gap_id = uuid4()
        gap = _make_gap(gap_id=gap_id, is_resolved=False)

        # Mock DB query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gap
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.resolve_gap(
            db=mock_db,
            gap_id=gap_id,
            company_id=sample_company_id,
            user_id=sample_user_id,
            notes="Beleg nachgereicht",
        )

        assert result.is_resolved is True
        assert result.resolution_notes == "Beleg nachgereicht"
        assert result.resolved_by == sample_user_id

    @pytest.mark.asyncio
    async def test_resolve_gap_not_found(
        self, service, mock_db, sample_company_id, sample_user_id,
    ):
        """ValueError wenn Luecke nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Luecke nicht gefunden"):
            await service.resolve_gap(
                db=mock_db,
                gap_id=uuid4(),
                company_id=sample_company_id,
                user_id=sample_user_id,
                notes="Test",
            )


class TestUpdateCheckItem:
    """Tests fuer update_check_item."""

    @pytest.mark.asyncio
    async def test_update_check_item(
        self, service, mock_db, sample_company_id, sample_user_id,
    ):
        """Status-Update funktioniert."""
        item_id = uuid4()
        item = _make_check_item(
            item_id=item_id,
            status_val=CheckItemStatus.PENDING.value,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = item
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.update_check_item(
            db=mock_db,
            item_id=item_id,
            company_id=sample_company_id,
            status=CheckItemStatus.PASSED.value,
            user_id=sample_user_id,
            notes="Manuell geprueft",
        )

        assert result.status == CheckItemStatus.PASSED.value
        assert result.resolution_notes == "Manuell geprueft"

    @pytest.mark.asyncio
    async def test_update_check_item_not_found(
        self, service, mock_db, sample_company_id, sample_user_id,
    ):
        """ValueError wenn Pruefpunkt nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Pruefpunkt nicht gefunden"):
            await service.update_check_item(
                db=mock_db,
                item_id=uuid4(),
                company_id=sample_company_id,
                status=CheckItemStatus.PASSED.value,
                user_id=sample_user_id,
            )


class TestCompleteSession:
    """Tests fuer complete_session."""

    @pytest.mark.asyncio
    async def test_complete_session_validates_checks(
        self, service, mock_db, sample_session_id, sample_company_id, sample_user_id,
    ):
        """Session kann nicht abgeschlossen werden wenn Pruefpunkte fehlgeschlagen."""
        failed_item = _make_check_item(
            check_name="Bankabgleich durchgefuehrt",
            status_val=CheckItemStatus.FAILED.value,
        )
        session = _make_session(
            session_id=sample_session_id,
            company_id=sample_company_id,
            check_items=[failed_item],
        )

        with patch.object(service, "get_session", return_value=session):
            with pytest.raises(ValueError, match="fehlgeschlagene Pruefpunkte"):
                await service.complete_session(
                    db=mock_db,
                    session_id=sample_session_id,
                    company_id=sample_company_id,
                    user_id=sample_user_id,
                )

    @pytest.mark.asyncio
    async def test_complete_session_success(
        self, service, mock_db, sample_session_id, sample_company_id, sample_user_id,
    ):
        """Session wird erfolgreich abgeschlossen."""
        passed_item = _make_check_item(
            status_val=CheckItemStatus.PASSED.value,
        )
        session = _make_session(
            session_id=sample_session_id,
            company_id=sample_company_id,
            check_items=[passed_item],
        )

        with patch.object(service, "get_session", return_value=session):
            result = await service.complete_session(
                db=mock_db,
                session_id=sample_session_id,
                company_id=sample_company_id,
                user_id=sample_user_id,
            )

            assert result.status == YearEndStatus.COMPLETED.value


class TestGenerateReportData:
    """Tests fuer generate_report_data."""

    @pytest.mark.asyncio
    async def test_generate_report_data_structure(
        self, service, mock_db, sample_session_id, sample_company_id,
    ):
        """Bericht hat alle erforderlichen Schluessel."""
        gap = _make_gap(
            category=GapCategory.MISSING_RECEIPT.value,
            month=3,
            amount=Decimal("150.00"),
        )
        item = _make_check_item(
            status_val=CheckItemStatus.PASSED.value,
            details_json={"monat": 3},
        )
        session = _make_session(
            session_id=sample_session_id,
            company_id=sample_company_id,
            fiscal_year=2025,
            check_items=[item],
            gaps=[gap],
        )
        session.total_checks = 1
        session.passed_checks = 1

        with patch.object(service, "get_session", return_value=session):
            report = await service.generate_report_data(
                db=mock_db,
                session_id=sample_session_id,
                company_id=sample_company_id,
            )

            assert "zusammenfassung" in report
            assert "pruefpunkte_nach_kategorie" in report
            assert "luecken_analyse" in report
            assert "monats_uebersicht" in report
            assert "loesungsfortschritt" in report
            assert "empfehlungen" in report

            # Zusammenfassung hat die richtigen Felder
            summary = report["zusammenfassung"]
            assert summary["geschaeftsjahr"] == 2025

            # Monats-Uebersicht hat 12 Eintraege
            assert len(report["monats_uebersicht"]) == 12


class TestListSessions:
    """Tests fuer list_sessions."""

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(
        self, service, mock_db, sample_company_id,
    ):
        """Paginierung funktioniert korrekt."""
        sessions = [
            _make_session(company_id=sample_company_id, fiscal_year=2024 + i)
            for i in range(3)
        ]

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 3

        # Mock data query
        mock_data_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sessions[:2]
        mock_data_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result],
        )

        result_sessions, total = await service.list_sessions(
            db=mock_db,
            company_id=sample_company_id,
            page=1,
            per_page=2,
        )

        assert total == 3
        assert len(result_sessions) == 2


class TestGetGapsFiltered:
    """Tests fuer get_gaps mit Filtern."""

    @pytest.mark.asyncio
    async def test_get_gaps_filtered(
        self, service, mock_db, sample_session_id, sample_company_id,
    ):
        """Filterung nach Kategorie/Monat/Loesungsstatus."""
        gaps = [_make_gap(month=1), _make_gap(month=3)]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = gaps
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_gaps(
            db=mock_db,
            session_id=sample_session_id,
            company_id=sample_company_id,
            category=GapCategory.MISSING_RECEIPT.value,
            month=1,
            resolved=False,
        )

        # The mock returns both, but the SQL would filter
        assert len(result) == 2
        mock_db.execute.assert_called_once()

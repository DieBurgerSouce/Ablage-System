# -*- coding: utf-8 -*-
"""Unit-Tests fuer Dashboard-KPI-Anbindung (W1-010).

Testet:
- AccountService.get_total_balance (company-scoped Kontostand-Summe)
- _get_cash_flow_kpis bindet den echten Kontostand an (kein 0.0-Hardcode mehr)
- _get_ocr_quality_kpis bindet OCRQualityMetricsService.get_ocr_quality_summary an
- get_ocr_quality_summary liefert ocr_processed_count (ehrlicher Nenner)
- /dashboard/kpis nutzt get_user_company_id_dep (Multi-Tenant, kein getattr-Pattern)
"""

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.api.v1.dashboard import (
    _get_cash_flow_kpis,
    _get_ocr_quality_kpis,
    get_aggregated_kpis,
)
from app.services.banking.account_service import AccountService
from app.services.ocr_quality_metrics_service import OCRQualityMetricsService

TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= AccountService.get_total_balance =========================


class TestGetTotalBalance:
    """Tests fuer die company-scoped Kontostand-Summe."""

    @pytest.mark.asyncio
    async def test_sums_balances(self) -> None:
        """Summiert current_balance ueber aktive Konten."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("1234.56")
        mock_db.execute.return_value = mock_result

        total = await AccountService().get_total_balance(mock_db, TEST_COMPANY_UUID)

        assert total == Decimal("1234.56")
        mock_db.execute.assert_awaited_once()
        # Query muss company-gefiltert sein
        stmt = mock_db.execute.await_args.args[0]
        compiled = str(stmt)
        assert "company_id" in compiled
        assert "deleted_at" in compiled
        assert "is_active" in compiled

    @pytest.mark.asyncio
    async def test_no_accounts_returns_zero(self) -> None:
        """Keine Konten -> 0.00 statt None."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        total = await AccountService().get_total_balance(mock_db, TEST_COMPANY_UUID)

        assert total == Decimal("0.00")


# ========================= _get_cash_flow_kpis =========================


class TestCashFlowKPIsBalance:
    """Tests fuer die Kontostand-Anbindung in den Cashflow-KPIs."""

    @pytest.mark.asyncio
    async def test_binds_real_balance(self) -> None:
        """current_balance kommt aus AccountService.get_total_balance."""
        mock_db = AsyncMock()

        with patch(
            "app.api.v1.dashboard.cash_flow_service"
        ) as mock_cf, patch(
            "app.api.v1.dashboard.AccountService"
        ) as mock_acc_cls:
            mock_cf.get_cash_flow_summary = AsyncMock(
                return_value={
                    "mid_term": {"inflow": 5000.0, "outflow": 2000.0, "net": 3000.0}
                }
            )
            mock_acc = MagicMock()
            mock_acc.get_total_balance = AsyncMock(return_value=Decimal("9876.54"))
            mock_acc_cls.return_value = mock_acc

            kpis = await _get_cash_flow_kpis(mock_db, TEST_COMPANY_UUID)

        assert kpis.current_balance == 9876.54
        assert kpis.expected_income_30d == 5000.0
        assert kpis.expected_expenses_30d == 2000.0
        assert kpis.net_cash_flow_30d == 3000.0
        assert kpis.trend == "positive"
        mock_acc.get_total_balance.assert_awaited_once_with(mock_db, TEST_COMPANY_UUID)

    @pytest.mark.asyncio
    async def test_without_company_returns_neutral(self) -> None:
        """Ohne Firmenzuordnung neutrale 0-Werte (kein Cross-Tenant-Leak)."""
        mock_db = AsyncMock()

        kpis = await _get_cash_flow_kpis(mock_db, None)

        assert kpis.current_balance == 0.0
        assert kpis.trend == "stable"
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_degrades_on_error(self) -> None:
        """Service-Fehler degradiert auf 0-Werte statt HTTP-500."""
        mock_db = AsyncMock()

        with patch("app.api.v1.dashboard.cash_flow_service") as mock_cf:
            mock_cf.get_cash_flow_summary = AsyncMock(
                side_effect=Exception("Verbindungsfehler")
            )
            kpis = await _get_cash_flow_kpis(mock_db, TEST_COMPANY_UUID)

        assert kpis.current_balance == 0.0
        assert kpis.trend == "stable"


# ========================= _get_ocr_quality_kpis =========================


def _mock_scalar_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    return result


class TestOCRQualityKPIs:
    """Tests fuer die OCR-Quality-Anbindung (G1-Kontrakt M3)."""

    @pytest.mark.asyncio
    async def test_binds_quality_summary(self) -> None:
        """success_rate/avg_confidence kommen aus dem DB-gestuetzten Service."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _mock_scalar_result(7)
        today_start = datetime(2026, 6, 12, tzinfo=timezone.utc)

        mock_service = MagicMock()
        mock_service.get_ocr_quality_summary = AsyncMock(
            return_value={
                "avg_confidence": 0.9123,
                "avg_german_quality": 0.95,
                "document_count": 12,
                "ocr_processed_count": 10,
                "low_quality_count": 2,
            }
        )

        with patch(
            "app.api.v1.dashboard.get_ocr_quality_metrics_service",
            return_value=mock_service,
        ):
            kpis = await _get_ocr_quality_kpis(mock_db, TEST_COMPANY_UUID, today_start)

        assert kpis.documents_today == 7
        # 10 verarbeitet, 2 low-quality -> 80.0 Prozent
        assert kpis.success_rate == 80.0
        assert kpis.avg_confidence == 0.912
        # Keine Datenquelle -> ehrlich None
        assert kpis.manual_corrections is None
        mock_service.get_ocr_quality_summary.assert_awaited_once_with(
            mock_db, TEST_COMPANY_UUID, since=today_start
        )

    @pytest.mark.asyncio
    async def test_no_processed_documents_returns_none(self) -> None:
        """Ohne OCR-verarbeitete Dokumente bleiben die Quoten None (ehrlich)."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _mock_scalar_result(0)
        today_start = datetime(2026, 6, 12, tzinfo=timezone.utc)

        mock_service = MagicMock()
        mock_service.get_ocr_quality_summary = AsyncMock(
            return_value={
                "avg_confidence": 0.0,
                "avg_german_quality": 0.0,
                "document_count": 0,
                "ocr_processed_count": 0,
                "low_quality_count": 0,
            }
        )

        with patch(
            "app.api.v1.dashboard.get_ocr_quality_metrics_service",
            return_value=mock_service,
        ):
            kpis = await _get_ocr_quality_kpis(mock_db, TEST_COMPANY_UUID, today_start)

        assert kpis.success_rate is None
        assert kpis.avg_confidence is None

    @pytest.mark.asyncio
    async def test_without_company_returns_none(self) -> None:
        """Ohne company_id keine mandantengetrennten Quoten -> None."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = _mock_scalar_result(3)
        today_start = datetime(2026, 6, 12, tzinfo=timezone.utc)

        kpis = await _get_ocr_quality_kpis(mock_db, None, today_start)

        assert kpis.documents_today == 3
        assert kpis.success_rate is None
        assert kpis.avg_confidence is None


# ========================= get_ocr_quality_summary =========================


class TestOCRQualitySummaryProcessedCount:
    """Tests fuer das additive ocr_processed_count-Feld."""

    @pytest.mark.asyncio
    async def test_summary_includes_processed_count(self) -> None:
        """Summary enthaelt ocr_processed_count (Count ueber non-NULL confidence)."""
        mock_db = AsyncMock()

        agg_result = MagicMock()
        agg_result.one.return_value = (12, 10, 0.88, 0.93)
        low_result = MagicMock()
        low_result.scalar.return_value = 2
        mock_db.execute.side_effect = [agg_result, low_result]

        service = OCRQualityMetricsService()
        summary = await service.get_ocr_quality_summary(
            mock_db, TEST_COMPANY_UUID, since=datetime(2026, 6, 1, tzinfo=timezone.utc)
        )

        assert summary["document_count"] == 12
        assert summary["ocr_processed_count"] == 10
        assert summary["low_quality_count"] == 2
        assert summary["avg_confidence"] == 0.88


# ========================= Endpoint-Wiring =========================


class TestKPIEndpointWiring:
    """Verifiziert das Multi-Tenant-Wiring des KPI-Endpoints."""

    def test_endpoint_uses_company_id_dependency(self) -> None:
        """get_aggregated_kpis nutzt get_user_company_id_dep statt getattr."""
        from app.api.dependencies import get_user_company_id_dep

        sig = inspect.signature(get_aggregated_kpis)
        assert "company_id" in sig.parameters
        default = sig.parameters["company_id"].default
        # FastAPI-Depends-Objekt mit der zentralen Company-Dependency
        assert getattr(default, "dependency", None) is get_user_company_id_dep

    def test_endpoint_source_has_no_getattr_pattern(self) -> None:
        """Das kaputte getattr(current_user, 'company_id')-Pattern ist entfernt."""
        source = inspect.getsource(get_aggregated_kpis)
        # Kein Code-Statement mehr, das company_id per getattr vom User holt
        # (der Docstring DARF das alte Pattern erwaehnen).
        assert "company_id = getattr" not in source

# -*- coding: utf-8 -*-
"""Unit-Tests fuer DPIA API (Multi-Tenant Isolation).

Schwerpunkt: K4-Fix aus MASTER_REVIEW_2026-05-19.md.
- company_id MUSS im SELECT-WHERE filtern (nicht nur Post-Fetch-Check)
- NULL company_id auf der Row MUSS Zugriff ablehnen (kein Legacy-Bypass)
- Cross-Tenant-Zugriff = 404 (timing-safe, kein Info-Leak)

Feinpoliert und durchdacht - DPIA Multi-Tenant Guards.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException, status


pytestmark = [pytest.mark.unit, pytest.mark.api, pytest.mark.security]


# ========================= Fixtures =========================


@pytest.fixture
def user_company_a():
    user = Mock()
    user.id = uuid4()
    user.company_id = uuid4()
    user.full_name = "Tester A"
    user.email = "a@example.com"
    return user


@pytest.fixture
def user_company_b():
    user = Mock()
    user.id = uuid4()
    user.company_id = uuid4()
    user.full_name = "Tester B"
    user.email = "b@example.com"
    return user


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_dpia(company_id):
    dpia = Mock()
    dpia.id = uuid4()
    dpia.title = "Test DPIA"
    dpia.company_id = company_id
    dpia.status = Mock(value="DRAFT")
    dpia.overall_risk_level = Mock(value="medium")
    dpia.assessment_date = None
    dpia.assessor_name = "Tester A"
    dpia.audit_trail = []
    dpia.to_dict = Mock(return_value={"id": str(dpia.id), "title": dpia.title})
    return dpia


# ================== get_dpia ==================


class TestGetDpiaMultiTenant:
    """K4: GET /{dpia_id} darf nur eigene Company sehen."""

    async def test_own_company_dpia_is_returned(self, user_company_a, mock_db):
        dpia = _make_dpia(user_company_a.company_id)
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_dpia

            result = await get_dpia(
                dpia_id=dpia.id, db=mock_db, current_user=user_company_a
            )

        # Service wurde mit company_id-Filter aufgerufen
        mock_svc.get_by_id.assert_awaited_once_with(
            mock_db, dpia.id, company_id=user_company_a.company_id
        )
        assert result == dpia.to_dict.return_value

    async def test_cross_tenant_returns_404(self, user_company_a, mock_db):
        """Service liefert None weil WHERE company_id=A nicht matched -> 404."""
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_dpia

            with pytest.raises(HTTPException) as exc:
                await get_dpia(
                    dpia_id=uuid4(), db=mock_db, current_user=user_company_a
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_null_company_id_on_row_is_rejected(
        self, user_company_a, mock_db
    ):
        """Legacy-Row mit NULL company_id darf NICHT durch defensive Check."""
        legacy_dpia = _make_dpia(company_id=None)
        mock_svc = Mock()
        # Service returnt die Row (z.B. wenn jemand Service-Filter umgeht)
        mock_svc.get_by_id = AsyncMock(return_value=legacy_dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_dpia

            with pytest.raises(HTTPException) as exc:
                await get_dpia(
                    dpia_id=legacy_dpia.id, db=mock_db, current_user=user_company_a
                )
        # 404 statt 403 -> kein Info-Leak ueber Existenz
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_different_company_id_on_row_is_rejected(
        self, user_company_a, user_company_b, mock_db
    ):
        """Row mit fremder company_id (sollte nicht passieren wenn Service korrekt
        filtert, aber Defense-in-Depth) wird abgelehnt."""
        foreign_dpia = _make_dpia(user_company_b.company_id)
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=foreign_dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_dpia

            with pytest.raises(HTTPException) as exc:
                await get_dpia(
                    dpia_id=foreign_dpia.id,
                    db=mock_db,
                    current_user=user_company_a,
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ================== update_dpia_status ==================


class TestUpdateDpiaStatusMultiTenant:
    """K4: PATCH /{dpia_id}/status reicht company_id an Service durch."""

    async def test_update_passes_company_id_to_service(
        self, user_company_a, mock_db
    ):
        dpia = _make_dpia(user_company_a.company_id)
        mock_svc = Mock()
        mock_svc.update_status = AsyncMock(return_value=dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import update_dpia_status, UpdateStatusRequest

            req = UpdateStatusRequest(status="review", comment="ok")
            await update_dpia_status(
                dpia_id=dpia.id,
                request=req,
                db=mock_db,
                current_user=user_company_a,
            )

        kwargs = mock_svc.update_status.await_args.kwargs
        assert kwargs["company_id"] == user_company_a.company_id

    async def test_cross_tenant_update_raises_404(self, user_company_a, mock_db):
        """Service wirft ValueError (nicht gefunden) bei Cross-Tenant -> 404."""
        mock_svc = Mock()
        mock_svc.update_status = AsyncMock(
            side_effect=ValueError("DPIA nicht gefunden")
        )

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import update_dpia_status, UpdateStatusRequest

            req = UpdateStatusRequest(status="review", comment="x")
            with pytest.raises(HTTPException) as exc:
                await update_dpia_status(
                    dpia_id=uuid4(),
                    request=req,
                    db=mock_db,
                    current_user=user_company_a,
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ================== add_dpo_consultation ==================


class TestAddDpoConsultationMultiTenant:
    async def test_passes_company_id(self, user_company_a, mock_db):
        dpia = _make_dpia(user_company_a.company_id)
        mock_svc = Mock()
        mock_svc.add_dpo_consultation = AsyncMock(return_value=dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import (
                add_dpo_consultation,
                DPOConsultationRequest,
            )

            req = DPOConsultationRequest(
                opinion="ok",
                recommendations=["use encryption"],
                approval=True,
                conditions=[],
            )
            await add_dpo_consultation(
                dpia_id=dpia.id,
                request=req,
                db=mock_db,
                current_user=user_company_a,
            )

        kwargs = mock_svc.add_dpo_consultation.await_args.kwargs
        assert kwargs["company_id"] == user_company_a.company_id


# ================== get_recommendations + audit-trail ==================


class TestRecommendationsAndAuditMultiTenant:
    async def test_recommendations_cross_tenant_returns_404(
        self, user_company_a, mock_db
    ):
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_recommendations

            with pytest.raises(HTTPException) as exc:
                await get_recommendations(
                    dpia_id=uuid4(),
                    db=mock_db,
                    current_user=user_company_a,
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_recommendations_null_company_id_rejected(
        self, user_company_a, mock_db
    ):
        legacy = _make_dpia(company_id=None)
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=legacy)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_recommendations

            with pytest.raises(HTTPException) as exc:
                await get_recommendations(
                    dpia_id=legacy.id,
                    db=mock_db,
                    current_user=user_company_a,
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_audit_trail_cross_tenant_returns_404(
        self, user_company_a, user_company_b, mock_db
    ):
        foreign = _make_dpia(user_company_b.company_id)
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=foreign)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_audit_trail

            with pytest.raises(HTTPException) as exc:
                await get_audit_trail(
                    dpia_id=foreign.id,
                    db=mock_db,
                    current_user=user_company_a,
                )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_audit_trail_passes_company_id(self, user_company_a, mock_db):
        dpia = _make_dpia(user_company_a.company_id)
        mock_svc = Mock()
        mock_svc.get_by_id = AsyncMock(return_value=dpia)

        with patch("app.api.v1.dpia.get_dpia_service", return_value=mock_svc):
            from app.api.v1.dpia import get_audit_trail

            result = await get_audit_trail(
                dpia_id=dpia.id, db=mock_db, current_user=user_company_a
            )
        mock_svc.get_by_id.assert_awaited_once_with(
            mock_db, dpia.id, company_id=user_company_a.company_id
        )
        assert result == dpia.audit_trail

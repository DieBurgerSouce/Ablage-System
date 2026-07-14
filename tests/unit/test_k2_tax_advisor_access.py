# -*- coding: utf-8 -*-
"""K2 (Trust-Folge, 2026-07-14): Steuerberater-Zugang muss (1) beim
Einladungs-Accept eine UserCompany-Zuordnung erhalten (sonst ist das Konto
im Multi-Tenancy-Modell funktional tot) und (2) nach Ablauf von
``access_until`` im zentralen Auth-Pfad abgewiesen werden (vorher wurde
das Feld gesetzt, aber nie geprueft).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.db.models import TaxAdvisorInviteStatus, UserCompany
from app.services.tax_advisor_service import TaxAdvisorService


def _pending_invite(company_id: uuid.UUID) -> MagicMock:
    invite = MagicMock()
    invite.id = uuid.uuid4()
    invite.company_id = company_id
    invite.email = "stb@kanzlei-test.de"
    invite.full_name = "Steuerberaterin Test"
    invite.status = TaxAdvisorInviteStatus.PENDING.value
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    invite.access_duration_days = 90
    invite.access_scope = None
    invite.invited_by_id = uuid.uuid4()
    return invite


def _result(scalar):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    return res


@pytest.mark.asyncio
async def test_accept_invite_legt_user_company_an():
    """Ohne user_companies-Zeile loest get_user_company_id/RLS keine Firma auf."""
    company_id = uuid.uuid4()
    invite = _pending_invite(company_id)
    role = MagicMock()

    db = AsyncMock()
    # Reihenfolge der Queries in accept_invite:
    # 1) Invite (FOR UPDATE), 2) existierender User?, 3) tax_advisor-Rolle
    db.execute.side_effect = [_result(invite), _result(None), _result(role)]
    db.add = MagicMock()

    service = TaxAdvisorService()
    user = await service.accept_invite(
        db=db, token="test-token-123", password="Sicher!Passwort#2026"
    )

    added = [call.args[0] for call in db.add.call_args_list]
    ucs = [obj for obj in added if isinstance(obj, UserCompany)]
    assert len(ucs) == 1, f"UserCompany fehlt (added: {[type(o).__name__ for o in added]})"
    uc = ucs[0]
    assert uc.company_id == company_id
    assert uc.user_id == user.id
    assert uc.role == "viewer"
    assert uc.is_current is True


@pytest.mark.asyncio
async def test_abgelaufener_access_until_wird_im_auth_pfad_abgewiesen(monkeypatch):
    """Abgelaufene befristete Konten duerfen KEINEN API-Zugriff mehr haben."""
    import app.api.dependencies as deps

    expired_user = MagicMock()
    expired_user.id = uuid.uuid4()
    expired_user.email = "stb@kanzlei-test.de"
    expired_user.is_active = True
    expired_user.access_until = datetime.now(timezone.utc) - timedelta(days=1)

    async def fake_decode_token(token):
        return {"sub": str(expired_user.id)}

    monkeypatch.setattr(deps, "decode_token", fake_decode_token)
    monkeypatch.setattr(deps, "verify_token_type", lambda payload, kind: None)
    monkeypatch.setattr(
        deps.UserService, "get_user_by_id", AsyncMock(return_value=expired_user)
    )

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(token="irrelevant", db=AsyncMock())

    assert exc_info.value.status_code == 403
    assert "abgelaufen" in exc_info.value.detail


@pytest.mark.asyncio
async def test_unbefristeter_user_passiert_access_until_pruefung(monkeypatch):
    """access_until=None (normale Konten) darf die Pruefung nicht ausloesen."""
    import app.api.dependencies as deps

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "ben@firmenich.de"
    user.is_active = True
    user.is_superuser = False
    user.access_until = None

    async def fake_decode_token(token):
        return {"sub": str(user.id)}

    monkeypatch.setattr(deps, "decode_token", fake_decode_token)
    monkeypatch.setattr(deps, "verify_token_type", lambda payload, kind: None)
    monkeypatch.setattr(
        deps.UserService, "get_user_by_id", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(deps, "set_rls_context", AsyncMock())
    monkeypatch.setattr(
        deps, "_resolve_accessible_company_ids", AsyncMock(return_value=[]),
        raising=False,
    )

    try:
        result = await deps.get_current_user(token="irrelevant", db=AsyncMock())
        assert result is user
    except HTTPException as exc:
        # Spaetere Schritte (Company-Aufloesung) duerfen scheitern —
        # nur die access_until-403 waere ein Regressionsfehler.
        assert "abgelaufen" not in exc.detail

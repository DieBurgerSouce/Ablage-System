# -*- coding: utf-8 -*-
"""Tests fuer den B2/M9-Produktions-Guard im Legacy-FinTSService.

Der Legacy-FinTSService liefert ausschliesslich Mock-Daten (keine echte
python-fints-Anbindung). In Produktion duerfen diese Methoden niemals
Fake-Daten liefern, eine TAN akzeptieren oder einen fiktiven Saldo
persistieren (B2/M9). Diese Tests sichern den zentralen Guard ab.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.services.banking.fints_service as fints_mod
from app.core.datetime_utils import utc_now
from app.services.banking.fints_service import (
    FinTSService,
    FinTSConnectionStatus,
    TANChallenge,
    TANMethod,
)


def _settings(env: str, allow_mock: bool = False) -> SimpleNamespace:
    return SimpleNamespace(ENVIRONMENT=env, FINTS_ALLOW_MOCK_SYNC=allow_mock)


@pytest.mark.parametrize(
    "env,blocked",
    [
        ("production", True),
        ("prod", True),
        ("PRODUCTION", True),
        ("development", False),
        ("staging", False),
        ("test", False),
    ],
)
def test_mock_blocked_in_production_helper(env: str, blocked: bool) -> None:
    """Der zentrale Helfer blockt genau in Produktion."""
    svc = FinTSService()
    with patch.object(fints_mod, "settings", _settings(env)):
        assert svc._mock_blocked_in_production("unit") is blocked


@pytest.mark.asyncio
async def test_get_balance_production_does_not_fabricate_or_persist() -> None:
    """get_balance darf in Produktion keinen Fake-Saldo liefern oder schreiben (B2/M9-Smoking-Gun)."""
    company_id = uuid4()
    account = MagicMock()
    account.company_id = company_id
    account.current_balance = None
    account.currency = "EUR"
    db = AsyncMock()
    db.get = AsyncMock(return_value=account)

    svc = FinTSService()
    with patch.object(fints_mod, "settings", _settings("production")):
        result = await svc.get_balance(db, uuid4(), company_id, pin="x")

    assert result is None
    assert account.current_balance is None  # kein fiktiver 1234.56-Saldo gesetzt
    db.commit.assert_not_awaited()  # nichts persistiert


@pytest.mark.asyncio
async def test_sync_transactions_production_returns_failure_no_save() -> None:
    """sync_transactions liefert in Produktion ein Fehlerergebnis und speichert keine Mocks."""
    company_id = uuid4()
    account = MagicMock()
    account.company_id = company_id
    account.iban = "DE00123456780000000000"
    db = AsyncMock()
    db.get = AsyncMock(return_value=account)

    svc = FinTSService()
    svc._save_transactions = AsyncMock()  # darf nicht aufgerufen werden
    with patch.object(fints_mod, "settings", _settings("production")):
        result = await svc.sync_transactions(db, uuid4(), company_id, pin="x")

    assert result.success is False
    assert "Produktion" in (result.error_message or "")
    svc._save_transactions.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_tan_production_no_auth_bypass() -> None:
    """confirm_tan darf in Produktion keine beliebige 6+-TAN akzeptieren (Auth-Bypass-Schutz)."""
    company_id = uuid4()
    account_id = uuid4()
    challenge_id = "cid-123"
    svc = FinTSService()
    svc._pending_tans[challenge_id] = TANChallenge(
        challenge_id=challenge_id,
        tan_method=TANMethod.PUSH_TAN,
        challenge_text="x",
        expires_at=utc_now() + timedelta(minutes=5),
    )
    svc._sessions["sid"] = {
        "account_id": account_id,
        "company_id": company_id,
        "status": FinTSConnectionStatus.AWAITING_TAN,
        "tan_challenge_id": challenge_id,
    }
    db = AsyncMock()

    with patch.object(fints_mod, "settings", _settings("production")):
        success, error = await svc.confirm_tan(db, challenge_id, "abcdef", company_id)

    assert success is False
    assert "Produktion" in (error or "")
    db.commit.assert_not_awaited()
    # Challenge bleibt bestehen, Status nicht auf CONNECTED gesetzt
    assert challenge_id in svc._pending_tans


@pytest.mark.asyncio
async def test_get_balance_allowed_outside_production() -> None:
    """Ausserhalb der Produktion bleibt der Mock fuer Entwicklung erlaubt."""
    company_id = uuid4()
    account = MagicMock()
    account.company_id = company_id
    account.current_balance = None
    account.currency = "EUR"
    db = AsyncMock()
    db.get = AsyncMock(return_value=account)

    svc = FinTSService()
    with patch.object(fints_mod, "settings", _settings("development")):
        result = await svc.get_balance(db, uuid4(), company_id, pin="x")

    assert result is not None  # Mock-Saldo im Dev-Modus

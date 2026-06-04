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
    return SimpleNamespace(
        ENVIRONMENT=env,
        FINTS_ALLOW_MOCK_SYNC=allow_mock,
        is_production=env.lower().startswith("prod"),
    )


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


# === Review-Erweiterungen (B2/M9-Haertung) ===

@pytest.mark.asyncio
async def test_sync_transactions_blocked_even_with_flag_in_production() -> None:
    """Selbst FINTS_ALLOW_MOCK_SYNC=True darf in Produktion keinen Mock buchen (Guard vor Flag)."""
    company_id = uuid4()
    account = MagicMock()
    account.company_id = company_id
    account.iban = "DE00123456780000000000"
    db = AsyncMock()
    db.get = AsyncMock(return_value=account)

    svc = FinTSService()
    svc._save_transactions = AsyncMock()
    with patch.object(fints_mod, "settings", _settings("production", allow_mock=True)):
        result = await svc.sync_transactions(db, uuid4(), company_id, pin="x")

    assert result.success is False
    svc._save_transactions.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_initiate_sepa_transfer_production_blocked() -> None:
    """initiate_sepa_transfer erzeugt in Produktion keine Fake-TAN-Challenge."""
    from decimal import Decimal
    company_id = uuid4()
    account = MagicMock()
    account.company_id = company_id
    db = AsyncMock()
    db.get = AsyncMock(return_value=account)

    svc = FinTSService()
    before = len(svc._pending_tans)
    with patch.object(fints_mod, "settings", _settings("production")):
        success, challenge, error = await svc.initiate_sepa_transfer(
            db, uuid4(), company_id, pin="x",
            beneficiary_name="ACME", beneficiary_iban="DE00123456780000000000",
            beneficiary_bic=None, amount=Decimal("100.00"), reference="Test",
        )

    assert success is False
    assert challenge is None
    assert "Produktion" in (error or "")
    assert len(svc._pending_tans) == before  # keine Challenge angelegt
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_enhanced_fints_no_mock_in_production_even_with_flag() -> None:
    """enhanced_fints._sync_connection darf in Produktion keine Mock-Transaktionen
    erzeugen/reconcilen — auch nicht bei FINTS_ALLOW_MOCK_SYNC=True (materiellste M9-Lücke)."""
    import app.services.banking.enhanced_fints_service as enh_mod
    from app.services.banking.enhanced_fints_service import get_enhanced_fints_service

    service = get_enhanced_fints_service()
    service._generate_mock_transactions = MagicMock(return_value=[{"id": "x", "amount": 99.0}])

    connection = MagicMock()
    connection.id = uuid4()
    connection.company_id = uuid4()
    connection.bank_name = "TestBank"
    connection.last_sync_at = None
    connection.accounts = []

    with patch.object(enh_mod, "settings", _settings("production", allow_mock=True)):
        result = await service._sync_connection(connection)

    service._generate_mock_transactions.assert_not_called()  # kein Mock in Prod
    assert result.transaction_count == 0

# -*- coding: utf-8 -*-
"""Unit-Tests fuer M13: automatischer Vorhersage-Feedback-Hook im Bank-Abgleich.

``AutoReconciliationService._record_delay_feedback`` schreibt beim Uebergang einer
Rechnung auf 'paid' ein ``PredictionFeedbackRecord`` (predicted vs. actual Verzug).
Damit sammelt der Cashflow-Backtest (M13) echte Daten. Der Hook muss:
- den tatsaechlichen Verzug korrekt berechnen (value_date - due_date),
- idempotent sein (kein Doppel-Feedback pro Rechnung),
- den Abgleich NIE abbrechen, wenn etwas schiefgeht.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.banking.auto_reconciliation_service import AutoReconciliationService

_PREDICTIVE = "app.services.ai.predictive_payment_service.get_predictive_payment_service"


class _AsyncCM:
    """Minimaler async-Context-Manager fuer db.begin_nested()."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _execute_result(existing_id=None) -> MagicMock:
    """Mockt das Ergebnis der Idempotenz-Abfrage (scalar_one_or_none)."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = existing_id
    return res


def _db(existing_id=None) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_execute_result(existing_id))
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    return db


def _invoice():
    return SimpleNamespace(
        id=uuid.uuid4(),
        due_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        company_id=uuid.uuid4(),
    )


def _tx(days_late: int = 8):
    return SimpleNamespace(
        value_date=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days_late),
        booking_date=None,
    )


@pytest.fixture
def service() -> AutoReconciliationService:
    return AutoReconciliationService()


@pytest.mark.asyncio
async def test_records_feedback_on_payment(service):
    """Beim paid-Uebergang wird predicted vs. actual Verzug persistiert."""
    db = _db(existing_id=None)
    invoice, tx, entity_id = _invoice(), _tx(days_late=8), uuid.uuid4()

    fake_predictive = SimpleNamespace(
        predict_payment_delay=AsyncMock(
            return_value=SimpleNamespace(predicted_delay_days=5.0)
        ),
        record_prediction_feedback=AsyncMock(),
    )

    with patch(_PREDICTIVE, return_value=fake_predictive):
        await service._record_delay_feedback(db, invoice, tx, entity_id)

    fake_predictive.record_prediction_feedback.assert_awaited_once()
    call = fake_predictive.record_prediction_feedback.await_args
    feedback = call.args[1]
    assert feedback.prediction_type == "delay"
    assert feedback.predicted_value == 5.0
    assert feedback.actual_value == 8.0  # value_date - due_date
    assert feedback.prediction_id == f"recon-delay:{invoice.id}"
    assert call.args[2] == invoice.company_id


@pytest.mark.asyncio
async def test_idempotent_skip_when_already_recorded(service):
    """Existiert bereits Feedback fuer die Rechnung, wird nichts erneut geschrieben."""
    db = _db(existing_id=uuid.uuid4())
    invoice, tx, entity_id = _invoice(), _tx(), uuid.uuid4()

    fake_predictive = SimpleNamespace(
        predict_payment_delay=AsyncMock(),
        record_prediction_feedback=AsyncMock(),
    )

    with patch(_PREDICTIVE, return_value=fake_predictive):
        await service._record_delay_feedback(db, invoice, tx, entity_id)

    fake_predictive.predict_payment_delay.assert_not_awaited()
    fake_predictive.record_prediction_feedback.assert_not_awaited()


@pytest.mark.asyncio
async def test_never_raises_and_skips_on_error(service):
    """Ein Fehler im Predictor darf den Abgleich nicht abbrechen (kein Raise)."""
    db = _db(existing_id=None)
    invoice, tx, entity_id = _invoice(), _tx(), uuid.uuid4()

    fake_predictive = SimpleNamespace(
        predict_payment_delay=AsyncMock(side_effect=RuntimeError("model down")),
        record_prediction_feedback=AsyncMock(),
    )

    with patch(_PREDICTIVE, return_value=fake_predictive):
        # Darf NICHT werfen.
        await service._record_delay_feedback(db, invoice, tx, entity_id)

    fake_predictive.record_prediction_feedback.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_without_entity_or_due_date(service):
    """Ohne Entity oder Faelligkeitsdatum wird gar nichts versucht (keine Query)."""
    db = _db(existing_id=None)

    # Kein entity_id
    await service._record_delay_feedback(db, _invoice(), _tx(), None)
    # Kein due_date
    invoice_no_due = SimpleNamespace(id=uuid.uuid4(), due_date=None, company_id=uuid.uuid4())
    await service._record_delay_feedback(db, invoice_no_due, _tx(), uuid.uuid4())

    db.execute.assert_not_awaited()

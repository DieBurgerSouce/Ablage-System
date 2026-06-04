# -*- coding: utf-8 -*-
"""Unit-Tests fuer den echten Cashflow-Backtest (M13).

`get_prediction_metrics` lieferte frueher eine Schaetzung (`is_estimated=True`).
Jetzt: echter Backtest aus gespeicherten Vorhersagen (PredictionFeedbackRecord);
nur ohne gespeicherte Daten faellt die Methode auf die Schaetzung zurueck.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.cashflow_prediction_service import CashflowPredictionService


def _res(scalars_list=None) -> MagicMock:
    res = MagicMock()
    res.scalars.return_value.all.return_value = scalars_list if scalars_list is not None else []
    return res


@pytest.fixture
def service() -> CashflowPredictionService:
    return CashflowPredictionService(db=AsyncMock())


@pytest.mark.asyncio
async def test_real_backtest_from_stored_feedback(service):
    """Mit gespeicherten Vorhersagen werden echte Metriken (is_estimated=False) geliefert."""
    cid = uuid.uuid4()
    records = [
        SimpleNamespace(was_accurate=True, predicted_value=3.0, actual_value=4.0, company_id=cid),
        SimpleNamespace(was_accurate=False, predicted_value=2.0, actual_value=10.0, company_id=cid),
    ]
    service.db.execute = AsyncMock(side_effect=[_res(records)])

    m = await service.get_prediction_metrics(cid)

    assert m.is_estimated is False
    assert m.total_predictions == 2
    assert m.correct_predictions == 1
    assert m.accuracy_rate == 50.0
    # MAE = mean(|3-4|, |2-10|) = mean(1, 8) = 4.5
    assert m.mean_absolute_error_days == 4.5


@pytest.mark.asyncio
async def test_fallback_to_estimate_without_feedback(service):
    """Ohne gespeicherte Vorhersagen faellt die Methode transparent auf die Schaetzung zurueck."""
    cid = uuid.uuid4()
    # 1. Aufruf: PredictionFeedbackRecord leer; 2. Aufruf: paid InvoiceTracking leer
    service.db.execute = AsyncMock(side_effect=[_res([]), _res([])])

    m = await service.get_prediction_metrics(cid)

    assert m.is_estimated is True
    assert m.total_predictions == 0

# -*- coding: utf-8 -*-
"""F-REC-2 (Reconcile 2026-07): Best-Effort-Schreibpfade dürfen nicht mehr
STILL scheitern — geschluckte Fehler müssen die Prometheus-Metrik
``ablage_best_effort_write_failures_total`` erhöhen.

Hintergrund: Genau dieses try/except-Muster hat den Feature-Toggle-
Audit-Trail monatelang unbemerkt verschluckt (feature_toggle_history
fehlte auf Live, der INSERT scheiterte, der except-Block loggte nur).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY

from app.services.feature_toggle_admin_service import _write_history


def _counter_value(operation: str) -> float:
    value = REGISTRY.get_sample_value(
        "ablage_best_effort_write_failures_total",
        {"operation": operation},
    )
    return value or 0.0


def _fake_flag() -> MagicMock:
    flag = MagicMock()
    flag.id = uuid.uuid4()
    flag.key = "test-flag"
    return flag


@pytest.mark.asyncio
async def test_write_history_fehler_erhoeht_best_effort_metrik():
    """DB-Fehler beim History-INSERT wird geschluckt, ABER gezählt."""
    before = _counter_value("feature_toggle_history_insert")

    db = AsyncMock()
    db.execute.side_effect = RuntimeError("relation feature_toggle_history does not exist")

    # Darf NICHT raisen (best-effort by design) ...
    await _write_history(
        db,
        flag=_fake_flag(),
        action="enabled",
        old_value={"enabled": False},
        new_value={"enabled": True},
        changed_by_id=None,
        reason="test",
    )

    # ... aber MUSS den stillen Verlust sichtbar machen (Alert-Grundlage).
    after = _counter_value("feature_toggle_history_insert")
    assert after == before + 1


@pytest.mark.asyncio
async def test_write_history_erfolg_zaehlt_nicht():
    """Erfolgreiche Writes erhöhen die Verlust-Metrik nicht."""
    before = _counter_value("feature_toggle_history_insert")

    db = AsyncMock()
    await _write_history(
        db,
        flag=_fake_flag(),
        action="disabled",
        old_value=None,
        new_value=None,
        changed_by_id=None,
        reason=None,
    )

    assert _counter_value("feature_toggle_history_insert") == before
    db.execute.assert_awaited_once()

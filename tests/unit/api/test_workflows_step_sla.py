# -*- coding: utf-8 -*-
"""Tests: _compute_step_sla (workflows.py) - SLA pro Workflow-Knoten.

Ersetzt den frueheren Placeholder (sla_deadline/sla_status waren immer
None). SLA-Quelle ist die Step-Config (sla_minutes bzw. timeout_seconds);
ohne Konfiguration bleibt der Wert ehrlich None.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.api.v1.workflows import _compute_step_sla


def _step(config: dict) -> MagicMock:
    step = MagicMock()
    step.config = config
    return step


NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)


class TestComputeStepSla:
    def test_ohne_sla_config_ehrlich_none(self) -> None:
        deadline, status = _compute_step_sla(_step({}), NOW, NOW)
        assert deadline is None
        assert status is None

    def test_ohne_startzeit_ehrlich_none(self) -> None:
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), None, None
        )
        assert deadline is None
        assert status is None

    def test_abschluss_innerhalb_sla_ist_ok(self) -> None:
        started = NOW
        completed = NOW + timedelta(minutes=5)
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), started, completed
        )
        assert deadline == started + timedelta(minutes=30)
        assert status == "ok"

    def test_abschluss_nach_deadline_ist_breached(self) -> None:
        started = NOW
        completed = NOW + timedelta(minutes=45)
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), started, completed
        )
        assert deadline == started + timedelta(minutes=30)
        assert status == "breached"

    def test_laufender_schritt_ueber_80_prozent_ist_warning(self) -> None:
        # Schritt laeuft seit 29 Minuten bei 30-Minuten-SLA
        started = datetime.now(timezone.utc) - timedelta(minutes=29)
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), started, None
        )
        assert deadline is not None
        assert status == "warning"

    def test_laufender_schritt_nach_deadline_ist_breached(self) -> None:
        started = datetime.now(timezone.utc) - timedelta(minutes=31)
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), started, None
        )
        assert status == "breached"

    def test_timeout_seconds_fallback(self) -> None:
        started = NOW
        completed = NOW + timedelta(seconds=10)
        deadline, status = _compute_step_sla(
            _step({"timeout_seconds": 120}), started, completed
        )
        assert deadline == started + timedelta(seconds=120)
        assert status == "ok"

    def test_sla_minutes_hat_vorrang_vor_timeout_seconds(self) -> None:
        started = NOW
        deadline, _ = _compute_step_sla(
            _step({"sla_minutes": 60, "timeout_seconds": 120}),
            started,
            started + timedelta(minutes=1),
        )
        assert deadline == started + timedelta(minutes=60)

    def test_naive_zeitstempel_als_utc(self) -> None:
        started = datetime(2026, 6, 12, 12, 0, 0)  # naiv
        completed = datetime(2026, 6, 12, 12, 10, 0)  # naiv
        deadline, status = _compute_step_sla(
            _step({"sla_minutes": 30}), started, completed
        )
        assert deadline is not None
        assert deadline.tzinfo is not None
        assert status == "ok"

    def test_ungueltige_konfigwerte_ergeben_none(self) -> None:
        for bad in ({"sla_minutes": 0}, {"sla_minutes": -5},
                    {"sla_minutes": "30"}, {"timeout_seconds": "abc"}):
            deadline, status = _compute_step_sla(_step(bad), NOW, NOW)
            assert deadline is None
            assert status is None

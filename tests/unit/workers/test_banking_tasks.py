# -*- coding: utf-8 -*-
"""
Tests fuer Banking Celery Tasks.

Testet:
- Beat Schedule Konfiguration
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen

HINWEIS: Die Banking-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4


class TestBankingBeatSchedule:
    """Tests fuer Banking Celery Beat Schedule Konfiguration."""

    def test_beat_schedule_is_defined(self):
        """Sollte Beat Schedule definiert haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert BANKING_BEAT_SCHEDULE is not None
        assert isinstance(BANKING_BEAT_SCHEDULE, dict)

    def test_beat_schedule_contains_auto_reconcile(self):
        """Sollte auto reconcile Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-auto-reconcile-hourly" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-auto-reconcile-hourly"]
        assert "task" in config
        assert "schedule" in config
        assert config["task"] == "app.workers.tasks.banking_tasks.auto_reconcile"

    def test_beat_schedule_contains_update_balances(self):
        """Sollte update balances Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-update-balances-daily" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-update-balances-daily"]
        assert config["task"] == "app.workers.tasks.banking_tasks.update_account_balances"

    def test_beat_schedule_contains_check_overdue(self):
        """Sollte check overdue Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-check-overdue-daily" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-check-overdue-daily"]
        assert config["task"] == "app.workers.tasks.banking_tasks.check_overdue_payments"

    def test_beat_schedule_contains_dunning(self):
        """Sollte dunning Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-process-dunning-daily" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-process-dunning-daily"]
        assert config["task"] == "app.workers.tasks.banking_tasks.process_automatic_dunning"

    def test_beat_schedule_contains_cash_flow(self):
        """Sollte cash flow Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-update-cash-flow-4h" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-update-cash-flow-4h"]
        assert config["task"] == "app.workers.tasks.banking_tasks.update_cash_flow_forecasts"

    def test_beat_schedule_contains_skonto_alerts(self):
        """Sollte skonto alerts Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-skonto-alerts-morning" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-skonto-alerts-morning"]
        assert config["task"] == "app.workers.tasks.banking_tasks.send_skonto_alerts"

    def test_beat_schedule_contains_tan_cleanup(self):
        """Sollte TAN cleanup Task im Schedule haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        assert "banking-tan-cleanup-hourly" in BANKING_BEAT_SCHEDULE

        config = BANKING_BEAT_SCHEDULE["banking-tan-cleanup-hourly"]
        assert config["task"] == "app.workers.tasks.banking_tasks.cleanup_tan_challenges"

    def test_beat_schedule_has_valid_configs(self):
        """Sollte gueltige Konfigurationen haben."""
        from app.workers.tasks.banking_tasks import BANKING_BEAT_SCHEDULE

        for task_name, config in BANKING_BEAT_SCHEDULE.items():
            assert "task" in config, f"Task {task_name} hat keine task-Definition"
            assert "schedule" in config, f"Task {task_name} hat keine schedule-Definition"

            # Validate queue option
            options = config.get("options", {})
            assert "queue" in options, f"Task {task_name} hat keine queue in options"


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_process_bank_import_is_registered(self):
        """Sollte process_bank_import Task registriert haben."""
        from app.workers.tasks.banking_tasks import process_bank_import

        assert process_bank_import is not None
        assert hasattr(process_bank_import, 'name')
        assert process_bank_import.name == "app.workers.tasks.banking_tasks.process_bank_import"

    def test_auto_reconcile_is_registered(self):
        """Sollte auto_reconcile Task registriert haben."""
        from app.workers.tasks.banking_tasks import auto_reconcile

        assert auto_reconcile is not None
        assert hasattr(auto_reconcile, 'name')
        assert auto_reconcile.name == "app.workers.tasks.banking_tasks.auto_reconcile"

    def test_parse_transaction_references_is_registered(self):
        """Sollte parse_transaction_references Task registriert haben."""
        from app.workers.tasks.banking_tasks import parse_transaction_references

        assert parse_transaction_references is not None
        assert hasattr(parse_transaction_references, 'name')
        assert parse_transaction_references.name == "app.workers.tasks.banking_tasks.parse_transaction_references"

    def test_update_account_balances_is_registered(self):
        """Sollte update_account_balances Task registriert haben."""
        from app.workers.tasks.banking_tasks import update_account_balances

        assert update_account_balances is not None
        assert hasattr(update_account_balances, 'name')
        assert update_account_balances.name == "app.workers.tasks.banking_tasks.update_account_balances"

    def test_check_overdue_payments_is_registered(self):
        """Sollte check_overdue_payments Task registriert haben."""
        from app.workers.tasks.banking_tasks import check_overdue_payments

        assert check_overdue_payments is not None
        assert hasattr(check_overdue_payments, 'name')
        assert check_overdue_payments.name == "app.workers.tasks.banking_tasks.check_overdue_payments"

    def test_process_automatic_dunning_is_registered(self):
        """Sollte process_automatic_dunning Task registriert haben."""
        from app.workers.tasks.banking_tasks import process_automatic_dunning

        assert process_automatic_dunning is not None
        assert hasattr(process_automatic_dunning, 'name')
        assert process_automatic_dunning.name == "app.workers.tasks.banking_tasks.process_automatic_dunning"

    def test_update_cash_flow_forecasts_is_registered(self):
        """Sollte update_cash_flow_forecasts Task registriert haben."""
        from app.workers.tasks.banking_tasks import update_cash_flow_forecasts

        assert update_cash_flow_forecasts is not None
        assert hasattr(update_cash_flow_forecasts, 'name')
        assert update_cash_flow_forecasts.name == "app.workers.tasks.banking_tasks.update_cash_flow_forecasts"

    def test_send_skonto_alerts_is_registered(self):
        """Sollte send_skonto_alerts Task registriert haben."""
        from app.workers.tasks.banking_tasks import send_skonto_alerts

        assert send_skonto_alerts is not None
        assert hasattr(send_skonto_alerts, 'name')
        assert send_skonto_alerts.name == "app.workers.tasks.banking_tasks.send_skonto_alerts"

    def test_cleanup_tan_challenges_is_registered(self):
        """Sollte cleanup_tan_challenges Task registriert haben."""
        from app.workers.tasks.banking_tasks import cleanup_tan_challenges

        assert cleanup_tan_challenges is not None
        assert hasattr(cleanup_tan_challenges, 'name')
        assert cleanup_tan_challenges.name == "app.workers.tasks.banking_tasks.cleanup_tan_challenges"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_process_bank_import_has_retry_config(self):
        """Sollte process_bank_import retry Konfiguration haben."""
        from app.workers.tasks.banking_tasks import process_bank_import

        # Check that max_retries is set
        assert hasattr(process_bank_import, 'max_retries')
        assert process_bank_import.max_retries == 3

    def test_auto_reconcile_has_retry_config(self):
        """Sollte auto_reconcile retry Konfiguration haben."""
        from app.workers.tasks.banking_tasks import auto_reconcile

        assert hasattr(auto_reconcile, 'max_retries')
        assert auto_reconcile.max_retries == 2

    def test_all_tasks_use_cpu_base(self):
        """Sollte alle Banking Tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.banking_tasks import (
            process_bank_import,
            auto_reconcile,
            parse_transaction_references,
            update_account_balances,
            check_overdue_payments,
            process_automatic_dunning,
            update_cash_flow_forecasts,
            send_skonto_alerts,
            cleanup_tan_challenges,
        )
        from app.workers.celery_app import CPUTask

        # All banking tasks are CPU-only (no GPU required)
        tasks = [
            process_bank_import,
            auto_reconcile,
            parse_transaction_references,
            update_account_balances,
            check_overdue_payments,
            process_automatic_dunning,
            update_cash_flow_forecasts,
            send_skonto_alerts,
            cleanup_tan_challenges,
        ]

        for task in tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.banking_tasks import (
            process_bank_import,
            auto_reconcile,
            parse_transaction_references,
            update_account_balances,
            check_overdue_payments,
            process_automatic_dunning,
            update_cash_flow_forecasts,
            send_skonto_alerts,
            cleanup_tan_challenges,
        )

        tasks = [
            process_bank_import,
            auto_reconcile,
            parse_transaction_references,
            update_account_balances,
            check_overdue_payments,
            process_automatic_dunning,
            update_cash_flow_forecasts,
            send_skonto_alerts,
            cleanup_tan_challenges,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.banking_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"


class TestRunAsyncHelper:
    """Tests fuer run_async Hilfsfunktion."""

    def test_run_async_success(self):
        """Sollte async Code korrekt ausfuehren."""
        from app.workers.tasks.banking_tasks import run_async

        async def sample_coro():
            return {"success": True}

        result = run_async(sample_coro())
        assert result == {"success": True}

    def test_run_async_with_exception(self):
        """Sollte Exceptions durchreichen."""
        from app.workers.tasks.banking_tasks import run_async

        async def failing_coro():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            run_async(failing_coro())

    def test_run_async_with_async_result(self):
        """Sollte async Ergebnisse korrekt zurueckgeben."""
        from app.workers.tasks.banking_tasks import run_async

        async def coro_with_data():
            return {
                "processed": 10,
                "matched": 5,
                "unmatched": 5,
            }

        result = run_async(coro_with_data())
        assert result["processed"] == 10
        assert result["matched"] == 5
        assert result["unmatched"] == 5

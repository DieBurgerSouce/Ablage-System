# -*- coding: utf-8 -*-
"""
Tests fuer Banking Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen
- Beat Schedule Integration in celery_app.py

HINWEIS: Die Banking-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4


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


# =============================================================================
# PHASE 1: Automatische Zahlungserinnerungen - Neue Tasks (Januar 2026)
# =============================================================================


class TestPreDueRemindersTask:
    """Tests fuer send_pre_due_reminders Task (Task 1.2)."""

    def test_send_pre_due_reminders_is_registered(self):
        """Sollte send_pre_due_reminders Task registriert haben."""
        from app.workers.tasks.banking_tasks import send_pre_due_reminders

        assert send_pre_due_reminders is not None
        assert hasattr(send_pre_due_reminders, 'name')
        assert send_pre_due_reminders.name == "app.workers.tasks.banking_tasks.send_pre_due_reminders"

    def test_send_pre_due_reminders_uses_cpu_base(self):
        """Sollte CPUTask Base verwenden."""
        from app.workers.tasks.banking_tasks import send_pre_due_reminders
        from app.workers.celery_app import CPUTask

        assert isinstance(send_pre_due_reminders, CPUTask)

    def test_send_pre_due_reminders_has_retry_config(self):
        """Sollte retry Konfiguration haben."""
        from app.workers.tasks.banking_tasks import send_pre_due_reminders

        assert hasattr(send_pre_due_reminders, 'max_retries')
        assert send_pre_due_reminders.max_retries >= 2


class TestDunningDailyReportTask:
    """Tests fuer generate_dunning_daily_report Task (Task 1.5)."""

    def test_generate_dunning_daily_report_is_registered(self):
        """Sollte generate_dunning_daily_report Task registriert haben."""
        from app.workers.tasks.banking_tasks import generate_dunning_daily_report

        assert generate_dunning_daily_report is not None
        assert hasattr(generate_dunning_daily_report, 'name')
        assert generate_dunning_daily_report.name == "app.workers.tasks.banking_tasks.generate_dunning_daily_report"

    def test_generate_dunning_daily_report_uses_cpu_base(self):
        """Sollte CPUTask Base verwenden."""
        from app.workers.tasks.banking_tasks import generate_dunning_daily_report
        from app.workers.celery_app import CPUTask

        assert isinstance(generate_dunning_daily_report, CPUTask)

    def test_generate_dunning_daily_report_has_retry_config(self):
        """Sollte retry Konfiguration haben."""
        from app.workers.tasks.banking_tasks import generate_dunning_daily_report

        assert hasattr(generate_dunning_daily_report, 'max_retries')
        assert generate_dunning_daily_report.max_retries >= 2


class TestDailyMahnlaufTask:
    """Tests fuer daily_mahnlauf Task (BGB §286 Compliance)."""

    def test_daily_mahnlauf_is_registered(self):
        """Sollte daily_mahnlauf Task registriert haben."""
        from app.workers.tasks.banking_tasks import daily_mahnlauf

        assert daily_mahnlauf is not None
        assert hasattr(daily_mahnlauf, 'name')
        assert daily_mahnlauf.name == "app.workers.tasks.banking_tasks.daily_mahnlauf"

    def test_daily_mahnlauf_uses_cpu_base(self):
        """Sollte daily_mahnlauf mit CPUTask Base konfigurieren."""
        from app.workers.tasks.banking_tasks import daily_mahnlauf
        from app.workers.celery_app import CPUTask

        assert isinstance(daily_mahnlauf, CPUTask)


class TestReactivateSnoozedTasksTask:
    """Tests fuer reactivate_snoozed_tasks Task."""

    def test_reactivate_snoozed_tasks_is_registered(self):
        """Sollte reactivate_snoozed_tasks Task registriert haben."""
        from app.workers.tasks.banking_tasks import reactivate_snoozed_tasks

        assert reactivate_snoozed_tasks is not None
        assert hasattr(reactivate_snoozed_tasks, 'name')
        assert reactivate_snoozed_tasks.name == "app.workers.tasks.banking_tasks.reactivate_snoozed_tasks"

    def test_reactivate_snoozed_tasks_uses_cpu_base(self):
        """Sollte reactivate_snoozed_tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.banking_tasks import reactivate_snoozed_tasks
        from app.workers.celery_app import CPUTask

        assert isinstance(reactivate_snoozed_tasks, CPUTask)


class TestCheckExpiredMahnstoppTask:
    """Tests fuer check_expired_mahnstopp Task."""

    def test_check_expired_mahnstopp_is_registered(self):
        """Sollte check_expired_mahnstopp Task registriert haben."""
        from app.workers.tasks.banking_tasks import check_expired_mahnstopp

        assert check_expired_mahnstopp is not None
        assert hasattr(check_expired_mahnstopp, 'name')
        assert check_expired_mahnstopp.name == "app.workers.tasks.banking_tasks.check_expired_mahnstopp"

    def test_check_expired_mahnstopp_uses_cpu_base(self):
        """Sollte check_expired_mahnstopp mit CPUTask Base konfigurieren."""
        from app.workers.tasks.banking_tasks import check_expired_mahnstopp
        from app.workers.celery_app import CPUTask

        assert isinstance(check_expired_mahnstopp, CPUTask)


class TestCeleryAppBeatScheduleIntegration:
    """Tests fuer celery_app.py Beat Schedule Integration."""

    def test_banking_beats_pruned_by_default_freeze(self):
        """Banking-Beats sind im Default-Freeze entfernt (Odoo-Neuausrichtung 2026-07).

        Banking/Mahnwesen uebernimmt Odoo (account_online_synchronization +
        account_followup); das banking-Modul ist per module_registry eingefroren
        und celery_app.py entfernt Include + Beats. Reaktivierung ueber
        ACTIVE_OPTIONAL_MODULES="banking".
        """
        from app.core.module_registry import is_module_active
        from app.workers.celery_app import celery_app

        assert not is_module_active("banking"), "banking muss im Default gefroren sein"

        beat_schedule = celery_app.conf.beat_schedule
        pruned_banking_tasks = [
            "banking-process-dunning-daily",
            "banking-daily-mahnlauf",
            "banking-reactivate-snoozed-tasks",
            "banking-check-expired-mahnstopp",
            "banking-pre-due-reminders-morning",
            "banking-skonto-alerts-morning",
            "banking-dunning-daily-report",
            "banking-update-cash-flow-4h",
            "banking-tan-cleanup-hourly",
        ]

        for task_name in pruned_banking_tasks:
            assert task_name not in beat_schedule, \
                f"Beat {task_name} muesste durch den banking-Freeze entfernt sein"

    def test_no_beat_entry_dispatches_banking_tasks(self):
        """Kein verbleibender Beat-Eintrag zeigt auf das eingefrorene banking_tasks-Modul."""
        from app.workers.celery_app import celery_app

        offending = [
            name
            for name, config in celery_app.conf.beat_schedule.items()
            if str(config.get("task", "")).startswith("app.workers.tasks.banking_tasks.")
        ]
        assert offending == [], \
            f"Beat-Eintraege dispatchen ins gefrorene banking_tasks-Modul: {offending}"

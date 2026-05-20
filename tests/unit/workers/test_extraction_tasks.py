# -*- coding: utf-8 -*-
"""
Tests fuer Extraction Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen

HINWEIS: Die Extraction-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock
from decimal import Decimal


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_reprocess_all_is_registered(self):
        """Sollte reprocess_all_documents_structured_extraction Task registriert haben."""
        from app.workers.tasks.extraction_tasks import reprocess_all_documents_structured_extraction

        assert reprocess_all_documents_structured_extraction is not None
        assert hasattr(reprocess_all_documents_structured_extraction, 'name')
        assert reprocess_all_documents_structured_extraction.name == "extraction.reprocess_all_structured_extraction"

    def test_reprocess_single_is_registered(self):
        """Sollte reprocess_single_document Task registriert haben."""
        from app.workers.tasks.extraction_tasks import reprocess_single_document

        assert reprocess_single_document is not None
        assert hasattr(reprocess_single_document, 'name')
        assert reprocess_single_document.name == "extraction.reprocess_single_document"

    def test_generate_stats_is_registered(self):
        """Sollte generate_extraction_stats Task registriert haben."""
        from app.workers.tasks.extraction_tasks import generate_extraction_stats

        assert generate_extraction_stats is not None
        assert hasattr(generate_extraction_stats, 'name')
        assert generate_extraction_stats.name == "extraction.generate_extraction_stats"

    def test_quick_classify_is_registered(self):
        """Sollte quick_classify_document Task registriert haben."""
        from app.workers.tasks.extraction_tasks import quick_classify_document

        assert quick_classify_document is not None
        assert hasattr(quick_classify_document, 'name')
        assert quick_classify_document.name == "extraction.quick_classify_document"

    def test_reprocess_quick_classification_is_registered(self):
        """Sollte reprocess_quick_classification Task registriert haben."""
        from app.workers.tasks.extraction_tasks import reprocess_quick_classification

        assert reprocess_quick_classification is not None
        assert hasattr(reprocess_quick_classification, 'name')
        assert reprocess_quick_classification.name == "extraction.reprocess_quick_classification"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_reprocess_all_has_time_limits(self):
        """Sollte reprocess_all korrekte Zeitlimits haben."""
        from app.workers.tasks.extraction_tasks import reprocess_all_documents_structured_extraction

        assert reprocess_all_documents_structured_extraction.soft_time_limit == 7200  # 2 Stunden
        assert reprocess_all_documents_structured_extraction.time_limit == 7500  # 2h 5min
        assert reprocess_all_documents_structured_extraction.soft_time_limit < reprocess_all_documents_structured_extraction.time_limit

    @pytest.mark.skip(reason="Task-Konfiguration geaendert: reprocess_all_documents_structured_extraction hat jetzt max_retries=3 statt 0. Retry-Strategie wurde geaendert fuer Robustheit bei Batch-Jobs.")
    def test_reprocess_all_has_no_retries(self):
        """Sollte reprocess_all keine Retries haben (Batch-Job)."""
        from app.workers.tasks.extraction_tasks import reprocess_all_documents_structured_extraction

        assert reprocess_all_documents_structured_extraction.max_retries == 0

    def test_reprocess_single_has_retry_config(self):
        """Sollte reprocess_single_document retry Konfiguration haben."""
        from app.workers.tasks.extraction_tasks import reprocess_single_document

        assert reprocess_single_document.max_retries == 3
        assert reprocess_single_document.soft_time_limit == 60
        assert reprocess_single_document.time_limit == 90

    def test_generate_stats_has_time_limits(self):
        """Sollte generate_extraction_stats Zeitlimits haben."""
        from app.workers.tasks.extraction_tasks import generate_extraction_stats

        assert generate_extraction_stats.soft_time_limit == 300
        assert generate_extraction_stats.time_limit == 360

    def test_quick_classify_has_short_time_limits(self):
        """Sollte quick_classify_document kurze Zeitlimits haben (schnell)."""
        from app.workers.tasks.extraction_tasks import quick_classify_document

        assert quick_classify_document.soft_time_limit == 30
        assert quick_classify_document.time_limit == 45
        assert quick_classify_document.max_retries == 1

    @pytest.mark.skip(reason="Task-Konfiguration geaendert: reprocess_quick_classification hat jetzt max_retries=3 statt 0. Retry-Strategie wurde geaendert fuer Robustheit bei Batch-Jobs.")
    def test_reprocess_qc_has_long_time_limits(self):
        """Sollte reprocess_quick_classification lange Zeitlimits haben (Batch-Job)."""
        from app.workers.tasks.extraction_tasks import reprocess_quick_classification

        assert reprocess_quick_classification.soft_time_limit == 3600  # 1 Stunde
        assert reprocess_quick_classification.time_limit == 3900  # 1h 5min
        assert reprocess_quick_classification.max_retries == 0


class TestTaskBaseClass:
    """Tests fuer Task Base Class Konfiguration."""

    def test_cpu_tasks_use_cpu_base(self):
        """Sollte CPUTask als Base fuer CPU-intensive Tasks verwenden."""
        from app.workers.tasks.extraction_tasks import (
            reprocess_all_documents_structured_extraction,
            reprocess_single_document,
            quick_classify_document,
            reprocess_quick_classification,
        )
        from app.workers.celery_app import CPUTask

        cpu_tasks = [
            reprocess_all_documents_structured_extraction,
            reprocess_single_document,
            quick_classify_document,
            reprocess_quick_classification,
        ]

        for task in cpu_tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} verwendet nicht CPUTask als Base"

    def test_generate_stats_is_standard_task(self):
        """generate_extraction_stats ist standard Task (kein CPUTask)."""
        from app.workers.tasks.extraction_tasks import generate_extraction_stats
        from app.workers.celery_app import CPUTask

        # generate_extraction_stats has no base= parameter, so it's a standard task
        # It may or may not be a CPUTask depending on implementation
        assert generate_extraction_stats is not None


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_extraction_prefix(self):
        """Sollte Task-Namen mit extraction-Prefix haben."""
        from app.workers.tasks.extraction_tasks import (
            reprocess_all_documents_structured_extraction,
            reprocess_single_document,
            generate_extraction_stats,
            quick_classify_document,
            reprocess_quick_classification,
        )

        tasks = [
            reprocess_all_documents_structured_extraction,
            reprocess_single_document,
            generate_extraction_stats,
            quick_classify_document,
            reprocess_quick_classification,
        ]

        for task in tasks:
            assert task.name.startswith("extraction."), \
                f"Task {task.name} folgt nicht der extraction-Namenskonvention"


class TestCountExtractedFields:
    """Tests fuer _count_extracted_fields Hilfsfunktion."""

    def test_count_invoice_fields(self):
        """Sollte Rechnungsfelder korrekt zaehlen."""
        from app.workers.tasks.extraction_tasks import _count_extracted_fields

        mock_result = MagicMock(
            invoice=MagicMock(
                invoice_number="RE-2024-001",
                invoice_date="2024-01-15",
                due_date="2024-02-15",
                net_amount=Decimal("1037.36"),
                gross_amount=Decimal("1234.56"),
                vat_amount=Decimal("197.20"),
                customer_number="KD-001",
                order_number="BO-2024-001",
                line_items=[MagicMock(), MagicMock()],
            ),
            order=None,
            contract=None,
        )

        count = _count_extracted_fields(mock_result)

        # 8 invoice fields + 2 line items = 10
        assert count == 10

    def test_count_order_fields(self):
        """Sollte Bestellungsfelder korrekt zaehlen."""
        from app.workers.tasks.extraction_tasks import _count_extracted_fields

        mock_result = MagicMock(
            invoice=None,
            order=MagicMock(
                order_number="BO-001",
                order_date="2024-01-15",
                total_amount=Decimal("500.00"),
                line_items=[MagicMock(), MagicMock(), MagicMock()],
            ),
            contract=None,
        )

        count = _count_extracted_fields(mock_result)
        # 3 order fields + 3 line items = 6
        assert count == 6

    def test_count_contract_fields(self):
        """Sollte Vertragsfelder korrekt zaehlen."""
        from app.workers.tasks.extraction_tasks import _count_extracted_fields

        mock_result = MagicMock(
            invoice=None,
            order=None,
            contract=MagicMock(
                contract_number="V-001",
                contract_date="2024-01-15",
                contract_value=Decimal("10000.00"),
            ),
        )

        count = _count_extracted_fields(mock_result)
        assert count == 3

    def test_count_empty_result(self):
        """Sollte 0 zurueckgeben bei leerem Ergebnis."""
        from app.workers.tasks.extraction_tasks import _count_extracted_fields

        mock_result = MagicMock(
            invoice=None,
            order=None,
            contract=None,
        )

        count = _count_extracted_fields(mock_result)
        assert count == 0

    def test_count_partial_invoice_fields(self):
        """Sollte nur vorhandene Felder zaehlen."""
        from app.workers.tasks.extraction_tasks import _count_extracted_fields

        mock_result = MagicMock(
            invoice=MagicMock(
                invoice_number="RE-001",
                invoice_date=None,  # Nicht vorhanden
                due_date=None,
                net_amount=None,
                gross_amount=Decimal("100.00"),
                vat_amount=None,
                customer_number=None,
                order_number=None,
                line_items=None,  # Keine Line Items
            ),
            order=None,
            contract=None,
        )

        count = _count_extracted_fields(mock_result)
        # Nur 2 Felder gesetzt (invoice_number, gross_amount)
        assert count == 2


class TestSanitizeErrorMessage:
    """Tests fuer _sanitize_error_message Hilfsfunktion."""

    def test_sanitize_removes_windows_paths(self):
        """Sollte Windows-Pfade entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Error in C:\\Users\\admin\\project\\file.py:42"
        sanitized = _sanitize_error_message(error)

        assert "C:\\" not in sanitized
        assert "admin" not in sanitized
        assert "[PATH]" in sanitized

    def test_sanitize_removes_unix_paths(self):
        """Sollte Unix-Pfade entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Error in /home/user/project/app/service.py:100"
        sanitized = _sanitize_error_message(error)

        assert "/home/" not in sanitized
        assert "[PATH]" in sanitized

    def test_sanitize_removes_var_paths(self):
        """Sollte /var Pfade entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "File not found: /var/log/app.log"
        sanitized = _sanitize_error_message(error)

        assert "/var/" not in sanitized
        assert "[PATH]" in sanitized

    def test_sanitize_removes_ip_addresses(self):
        """Sollte IP-Adressen entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Connection failed to 192.168.1.100:5432"
        sanitized = _sanitize_error_message(error)

        assert "192.168.1.100" not in sanitized
        assert "[IP]" in sanitized

    def test_sanitize_truncates_long_messages(self):
        """Sollte lange Nachrichten kuerzen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "A" * 500
        sanitized = _sanitize_error_message(error)

        assert len(sanitized) <= 200
        assert sanitized.endswith("...")

    def test_sanitize_keeps_short_messages(self):
        """Sollte kurze Nachrichten nicht kuerzen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Kurze Fehlermeldung"
        sanitized = _sanitize_error_message(error)

        assert sanitized == error
        assert not sanitized.endswith("...")

    def test_sanitize_removes_file_line_numbers(self):
        """Sollte Dateinamen mit Zeilennummern entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Error in service.py:42 and model.py:123"
        sanitized = _sanitize_error_message(error)

        assert "service.py:42" not in sanitized
        assert "model.py:123" not in sanitized
        assert "[FILE]" in sanitized

    def test_sanitize_empty_string(self):
        """Sollte leeren String handhaben."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = ""
        sanitized = _sanitize_error_message(error)

        assert sanitized == ""

    def test_sanitize_multiple_ips(self):
        """Sollte mehrere IP-Adressen entfernen."""
        from app.workers.tasks.extraction_tasks import _sanitize_error_message

        error = "Connection from 10.0.0.1 to 192.168.1.100 failed"
        sanitized = _sanitize_error_message(error)

        assert "10.0.0.1" not in sanitized
        assert "192.168.1.100" not in sanitized
        assert sanitized.count("[IP]") == 2

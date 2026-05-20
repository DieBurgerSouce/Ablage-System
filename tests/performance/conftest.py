# -*- coding: utf-8 -*-
"""
Pytest Configuration fuer Performance Tests.

Stellt Fixtures und Konfiguration fuer:
- OCR Performance Benchmarks
- Export Performance Tests
- Concurrent/Stress Tests
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from unittest.mock import Mock
from uuid import uuid4

import pytest

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def pytest_configure(config):
    """Registriere Custom Marker."""
    config.addinivalue_line(
        "markers",
        "performance: Performance/Benchmark Tests"
    )
    config.addinivalue_line(
        "markers",
        "benchmark: Benchmark Tests mit Zeitmessung"
    )
    config.addinivalue_line(
        "markers",
        "stress: Stress Tests mit hoher Last"
    )
    config.addinivalue_line(
        "markers",
        "slow: Langsame Tests (>30s)"
    )


# ==============================================================================
# Benchmark Results Directory
# ==============================================================================


@pytest.fixture(scope="session")
def benchmark_results_dir():
    """Erstelle Verzeichnis fuer Benchmark-Ergebnisse."""
    results_dir = Path(__file__).parent / "benchmark_results"
    results_dir.mkdir(exist_ok=True)
    return results_dir


# ==============================================================================
# Mock Document Fixtures
# ==============================================================================


@pytest.fixture
def mock_document_factory():
    """Factory fuer Mock-Dokumente."""
    def create_document(
        doc_id=None,
        text_size_kb=10,
        document_type="invoice"
    ):
        doc_id = doc_id or uuid4()

        # Generiere deutschen Text mit Umlauten
        base_text = (
            "Dies ist ein Testdokument fuer den Performance-Benchmark. "
            "Es enthaelt deutsche Umlaute wie aeoeue und sz. "
            "Rechnungsnummer: RE-2024-001. Betrag: 1.234,56 EUR. "
        )
        text = (base_text * ((text_size_kb * 1024) // len(base_text) + 1))[:text_size_kb * 1024]

        doc = Mock()
        doc.id = doc_id
        doc.filename = f"test_doc_{doc_id}.pdf"
        doc.document_type = document_type
        doc.status = "processed"
        doc.created_at = datetime.now(timezone.utc)
        doc.file_size = text_size_kb * 1024
        doc.page_count = max(1, text_size_kb // 2)
        doc.ocr_confidence = 0.85
        doc.extracted_text = text
        doc.detected_language = "de"
        doc.has_umlauts = True
        doc.document_metadata = {"test": True}
        doc.tags = []
        doc.ocr_backend_used = "mock"

        return doc

    return create_document


@pytest.fixture
def mock_documents_small(mock_document_factory) -> List[Mock]:
    """10 kleine Dokumente (1KB Text)."""
    return [mock_document_factory(text_size_kb=1) for _ in range(10)]


@pytest.fixture
def mock_documents_medium(mock_document_factory) -> List[Mock]:
    """50 mittlere Dokumente (10KB Text)."""
    return [mock_document_factory(text_size_kb=10) for _ in range(50)]


@pytest.fixture
def mock_documents_large(mock_document_factory) -> List[Mock]:
    """10 grosse Dokumente (100KB Text)."""
    return [mock_document_factory(text_size_kb=100) for _ in range(10)]


# ==============================================================================
# Timing Fixtures
# ==============================================================================


@pytest.fixture
def timer():
    """Einfacher Timer fuer Benchmarks."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.measurements = []

        def start(self):
            self.start_time = datetime.now()

        def stop(self):
            self.end_time = datetime.now()
            if self.start_time:
                elapsed = (self.end_time - self.start_time).total_seconds()
                self.measurements.append(elapsed)
                return elapsed
            return 0

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time).total_seconds()
            return 0

        @property
        def average(self):
            return sum(self.measurements) / len(self.measurements) if self.measurements else 0

    return Timer()


# ==============================================================================
# Resource Monitoring
# ==============================================================================


@pytest.fixture
def memory_tracker():
    """Memory-Tracker fuer Performance-Tests."""
    import tracemalloc

    class MemoryTracker:
        def __init__(self):
            self.snapshots = []
            self.peak_memory_mb = 0

        def start(self):
            tracemalloc.start()

        def snapshot(self):
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                self.snapshots.append({
                    "current_mb": current / 1024 / 1024,
                    "peak_mb": peak / 1024 / 1024,
                    "timestamp": datetime.now().isoformat()
                })
                self.peak_memory_mb = max(self.peak_memory_mb, peak / 1024 / 1024)

        def stop(self):
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        def get_peak_mb(self):
            return self.peak_memory_mb

    return MemoryTracker()

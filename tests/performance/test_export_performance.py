# -*- coding: utf-8 -*-
"""
Export Performance Test Suite.

Umfassende Performance-Tests fuer:
- Batch Export mit 100+ Dokumenten
- Concurrent Exports (10/100 parallel)
- Large File Exports (100MB+)
- Partial Failure Recovery
- Memory Efficiency

Ausfuehrung:
    pytest tests/performance/test_export_performance.py -v -m performance
    pytest tests/performance/test_export_performance.py -v -k "batch_100"

Ergebnisse werden in benchmark_results/ gespeichert.
"""

import asyncio
import io
import json
import statistics
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest

# ==============================================================================
# Configuration
# ==============================================================================


class ExportBenchmarkConfig:
    """Export Benchmark-Konfiguration."""

    # Performance-Ziele
    TARGETS = {
        "batch_100_max_seconds": 30.0,     # 100 Dokumente < 30s
        "batch_500_max_seconds": 120.0,    # 500 Dokumente < 2min
        "concurrent_10_max_seconds": 15.0,  # 10 parallele Exports < 15s
        "large_export_max_seconds": 60.0,   # 100MB Export < 60s
        "memory_limit_mb": 512,             # Max 512MB RAM pro Export
    }

    # Test-Konfiguration
    WARMUP_ITERATIONS = 2
    BENCHMARK_ITERATIONS = 5

    # Ergebnis-Verzeichnis
    RESULTS_DIR = Path(__file__).parent / "benchmark_results"


# ==============================================================================
# Helper Classes
# ==============================================================================


class ExportBenchmarkResult:
    """Speichert Export-Benchmark-Ergebnisse."""

    def __init__(self, name: str):
        self.name = name
        self.measurements: List[float] = []
        self.errors: List[str] = []
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.metadata: Dict = {}

    def add_measurement(self, value: float):
        self.measurements.append(value)

    def add_error(self, error: str):
        self.errors.append(error)

    def finalize(self):
        self.end_time = datetime.now(timezone.utc)

    @property
    def count(self) -> int:
        return len(self.measurements)

    @property
    def mean(self) -> float:
        return statistics.mean(self.measurements) if self.measurements else 0

    @property
    def median(self) -> float:
        return statistics.median(self.measurements) if self.measurements else 0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.measurements) if len(self.measurements) > 1 else 0

    @property
    def min_value(self) -> float:
        return min(self.measurements) if self.measurements else 0

    @property
    def max_value(self) -> float:
        return max(self.measurements) if self.measurements else 0

    @property
    def total(self) -> float:
        return sum(self.measurements)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "stdev": self.stdev,
            "min": self.min_value,
            "max": self.max_value,
            "total": self.total,
            "errors": len(self.errors),
            "error_details": self.errors[:10],  # Erste 10 Fehler
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "metadata": self.metadata,
            "timestamp": self.start_time.isoformat()
        }


def save_export_benchmark_result(result: ExportBenchmarkResult, config: ExportBenchmarkConfig):
    """Speichere Export-Benchmark-Ergebnis als JSON."""
    config.RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = config.RESULTS_DIR / f"export_{result.name}_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    return filename


# ==============================================================================
# Mock Document Generator
# ==============================================================================


class MockDocumentGenerator:
    """Generiert Mock-Dokumente fuer Performance-Tests."""

    @staticmethod
    def create_document(
        doc_id: Optional[UUID] = None,
        text_size_kb: int = 10,
        include_metadata: bool = True
    ) -> Mock:
        """Erstelle ein Mock-Dokument."""
        doc_id = doc_id or uuid4()

        # Generiere deutschen Text mit Umlauten
        base_text = (
            "Dies ist ein Testdokument fuer den Performance-Benchmark. "
            "Es enthaelt deutsche Umlaute wie aeoeue und sz. "
            "Rechnungsnummer: RE-2024-001. Betrag: 1.234,56 EUR. "
        )
        # Wiederhole bis gewuenschte Groesse erreicht
        text = (base_text * ((text_size_kb * 1024) // len(base_text) + 1))[:text_size_kb * 1024]

        doc = Mock()
        doc.id = doc_id
        doc.filename = f"benchmark_doc_{doc_id}.pdf"
        doc.document_type = "invoice"
        doc.status = "processed"
        doc.created_at = datetime.now(timezone.utc)
        doc.file_size = text_size_kb * 1024
        doc.page_count = max(1, text_size_kb // 2)
        doc.ocr_confidence = 0.85 + (hash(str(doc_id)) % 15) / 100
        doc.extracted_text = text
        doc.detected_language = "de"
        doc.has_umlauts = True
        doc.document_metadata = {"test": True, "benchmark": True} if include_metadata else {}
        doc.tags = []
        doc.ocr_backend_used = "mock"

        return doc

    @staticmethod
    def create_batch(count: int, text_size_kb: int = 10) -> List[Mock]:
        """Erstelle eine Batch von Mock-Dokumenten."""
        return [
            MockDocumentGenerator.create_document(text_size_kb=text_size_kb)
            for _ in range(count)
        ]


# ==============================================================================
# Mock Export Service
# ==============================================================================


class MockExportService:
    """Mock Export Service fuer Performance-Tests.

    Simuliert die echte Export-Logik ohne Datenbankzugriff.
    """

    async def batch_export(
        self,
        documents: List[Mock],
        format: str = "json",
        include_text: bool = True,
        include_metadata: bool = True,
        simulate_failure_rate: float = 0.0
    ) -> Tuple[bytes, str, Dict]:
        """Simuliere Batch-Export."""
        import random

        errors = []
        exported = []

        for doc in documents:
            # Simuliere zufaellige Fehler
            if simulate_failure_rate > 0 and random.random() < simulate_failure_rate:
                errors.append({
                    "document_id": str(doc.id),
                    "error": "Simulierter Fehler",
                    "error_code": "SIM_ERROR"
                })
                continue

            exported.append(doc)

        # Generiere Export basierend auf Format
        if format == "json":
            data, content_type = self._export_json(exported, include_text, include_metadata)
        elif format == "csv":
            data, content_type = self._export_csv(exported, include_text, include_metadata)
        elif format == "zip":
            data, content_type = self._export_zip(exported, include_text, include_metadata)
        else:
            data, content_type = self._export_json(exported, include_text, include_metadata)

        result = {
            "success": len(errors) == 0,
            "total_requested": len(documents),
            "processed": len(exported),
            "failed": len(errors),
            "errors": errors,
            "file_size_bytes": len(data)
        }

        return data, content_type, result

    def _export_json(
        self,
        documents: List[Mock],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als JSON."""
        export_data = []
        for doc in documents:
            item = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "file_size": doc.file_size,
                "page_count": doc.page_count,
                "ocr_confidence": doc.ocr_confidence,
            }

            if include_text:
                item["extracted_text"] = doc.extracted_text

            if include_metadata:
                item["metadata"] = doc.document_metadata
                item["detected_language"] = doc.detected_language

            export_data.append(item)

        return json.dumps(export_data, ensure_ascii=False).encode("utf-8"), "application/json"

    def _export_csv(
        self,
        documents: List[Mock],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als CSV."""
        import csv

        output = io.StringIO()
        fieldnames = ["id", "filename", "document_type", "status", "file_size", "page_count"]

        if include_text:
            fieldnames.append("extracted_text")
        if include_metadata:
            fieldnames.extend(["detected_language"])

        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for doc in documents:
            row = {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "file_size": doc.file_size,
                "page_count": doc.page_count,
            }

            if include_text:
                text = doc.extracted_text or ""
                row["extracted_text"] = text[:1000] + "..." if len(text) > 1000 else text

            if include_metadata:
                row["detected_language"] = doc.detected_language or ""

            writer.writerow(row)

        # UTF-8 BOM fuer Excel
        return ("\ufeff" + output.getvalue()).encode("utf-8"), "text/csv"

    def _export_zip(
        self,
        documents: List[Mock],
        include_text: bool,
        include_metadata: bool
    ) -> Tuple[bytes, str]:
        """Export als ZIP."""
        output = io.BytesIO()

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                item = {
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "document_type": doc.document_type,
                    "file_size": doc.file_size,
                }

                if include_text:
                    item["extracted_text"] = doc.extracted_text

                if include_metadata:
                    item["metadata"] = doc.document_metadata

                json_content = json.dumps(item, ensure_ascii=False, indent=2)
                filename = f"{doc.filename.rsplit('.', 1)[0]}_{doc.id}.json"
                zf.writestr(filename, json_content.encode("utf-8"))

        return output.getvalue(), "application/zip"


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(scope="module")
def export_benchmark_config():
    """Export-Benchmark-Konfiguration."""
    config = ExportBenchmarkConfig()
    config.RESULTS_DIR.mkdir(exist_ok=True)
    return config


@pytest.fixture
def mock_export_service():
    """Mock Export Service."""
    return MockExportService()


@pytest.fixture
def document_generator():
    """Dokument-Generator."""
    return MockDocumentGenerator()


@pytest.fixture
def sample_documents_100(document_generator):
    """100 Test-Dokumente."""
    return document_generator.create_batch(100, text_size_kb=5)


@pytest.fixture
def sample_documents_500(document_generator):
    """500 Test-Dokumente."""
    return document_generator.create_batch(500, text_size_kb=5)


@pytest.fixture
def large_documents_10(document_generator):
    """10 grosse Dokumente (je 1MB Text)."""
    return document_generator.create_batch(10, text_size_kb=1024)


# ==============================================================================
# Batch Export Performance Tests
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestBatchExportPerformance:
    """Performance-Tests fuer Batch-Exports."""

    async def test_batch_export_100_documents_json(
        self,
        export_benchmark_config,
        mock_export_service,
        sample_documents_100
    ):
        """Benchmark: 100 Dokumente als JSON < 30 Sekunden."""
        result = ExportBenchmarkResult("batch_100_json")

        # Warmup
        for _ in range(export_benchmark_config.WARMUP_ITERATIONS):
            await mock_export_service.batch_export(
                sample_documents_100[:10], format="json"
            )

        # Benchmark
        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await mock_export_service.batch_export(
                sample_documents_100, format="json"
            )
            duration = time.time() - start
            result.add_measurement(duration)

            # Validierung
            assert export_result["processed"] == 100
            assert len(data) > 0
            assert content_type == "application/json"

        result.metadata["documents"] = 100
        result.metadata["format"] = "json"
        result.metadata["target_seconds"] = export_benchmark_config.TARGETS["batch_100_max_seconds"]
        result.metadata["avg_file_size_mb"] = len(data) / 1024 / 1024
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Assertion: Durchschnitt unter Ziel
        assert result.mean < export_benchmark_config.TARGETS["batch_100_max_seconds"], \
            f"Batch-100 Export dauerte {result.mean:.2f}s (Ziel: {export_benchmark_config.TARGETS['batch_100_max_seconds']}s)"

    async def test_batch_export_100_documents_csv(
        self,
        export_benchmark_config,
        mock_export_service,
        sample_documents_100
    ):
        """Benchmark: 100 Dokumente als CSV < 30 Sekunden."""
        result = ExportBenchmarkResult("batch_100_csv")

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await mock_export_service.batch_export(
                sample_documents_100, format="csv"
            )
            duration = time.time() - start
            result.add_measurement(duration)

            assert export_result["processed"] == 100
            assert content_type == "text/csv"

        result.metadata["documents"] = 100
        result.metadata["format"] = "csv"
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        assert result.mean < export_benchmark_config.TARGETS["batch_100_max_seconds"]

    async def test_batch_export_100_documents_zip(
        self,
        export_benchmark_config,
        mock_export_service,
        sample_documents_100
    ):
        """Benchmark: 100 Dokumente als ZIP < 30 Sekunden."""
        result = ExportBenchmarkResult("batch_100_zip")

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await mock_export_service.batch_export(
                sample_documents_100, format="zip"
            )
            duration = time.time() - start
            result.add_measurement(duration)

            assert export_result["processed"] == 100
            assert content_type == "application/zip"

            # Validiere ZIP-Inhalt
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                assert len(zf.namelist()) == 100

        result.metadata["documents"] = 100
        result.metadata["format"] = "zip"
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        assert result.mean < export_benchmark_config.TARGETS["batch_100_max_seconds"]

    async def test_batch_export_500_documents(
        self,
        export_benchmark_config,
        mock_export_service,
        sample_documents_500
    ):
        """Benchmark: 500 Dokumente < 120 Sekunden."""
        result = ExportBenchmarkResult("batch_500_json")

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await mock_export_service.batch_export(
                sample_documents_500, format="json"
            )
            duration = time.time() - start
            result.add_measurement(duration)

            assert export_result["processed"] == 500

        result.metadata["documents"] = 500
        result.metadata["format"] = "json"
        result.metadata["target_seconds"] = export_benchmark_config.TARGETS["batch_500_max_seconds"]
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        assert result.mean < export_benchmark_config.TARGETS["batch_500_max_seconds"], \
            f"Batch-500 Export dauerte {result.mean:.2f}s (Ziel: {export_benchmark_config.TARGETS['batch_500_max_seconds']}s)"


# ==============================================================================
# Concurrent Export Tests
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestConcurrentExportPerformance:
    """Performance-Tests fuer parallele Exports."""

    async def test_concurrent_exports_10(
        self,
        export_benchmark_config,
        document_generator
    ):
        """10 parallele Exports sollten nicht zu Konflikten fuehren."""
        result = ExportBenchmarkResult("concurrent_10")
        service = MockExportService()

        # 10 parallele Export-Batches (je 20 Dokumente)
        batches = [document_generator.create_batch(20) for _ in range(10)]

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()

            # Starte alle Exports parallel
            tasks = [
                asyncio.create_task(service.batch_export(batch, format="json"))
                for batch in batches
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start
            result.add_measurement(duration)

            # Validiere alle Ergebnisse
            successful = 0
            for res in results:
                if isinstance(res, Exception):
                    result.add_error(str(res))
                else:
                    data, content_type, export_result = res
                    if export_result["success"]:
                        successful += 1

            result.metadata["successful_exports"] = successful

        result.metadata["parallel_exports"] = 10
        result.metadata["documents_per_export"] = 20
        result.metadata["total_documents"] = 200
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Alle 10 Exports sollten erfolgreich sein
        assert result.metadata.get("successful_exports", 0) == 10
        assert result.mean < export_benchmark_config.TARGETS["concurrent_10_max_seconds"]

    async def test_concurrent_exports_stress(
        self,
        export_benchmark_config,
        document_generator
    ):
        """Stress-Test: 50 parallele Exports."""
        result = ExportBenchmarkResult("concurrent_50_stress")
        service = MockExportService()

        # 50 parallele Export-Batches (je 10 Dokumente)
        batches = [document_generator.create_batch(10) for _ in range(50)]

        start = time.time()

        # Starte alle Exports parallel
        tasks = [
            asyncio.create_task(service.batch_export(batch, format="json"))
            for batch in batches
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start
        result.add_measurement(duration)

        # Zaehle Erfolge und Fehler
        successful = sum(
            1 for res in results
            if not isinstance(res, Exception) and res[2]["success"]
        )
        failed = len(results) - successful

        result.metadata["parallel_exports"] = 50
        result.metadata["documents_per_export"] = 10
        result.metadata["successful"] = successful
        result.metadata["failed"] = failed
        result.metadata["success_rate"] = successful / 50
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Mindestens 95% Erfolgsrate
        assert result.metadata["success_rate"] >= 0.95, \
            f"Erfolgsrate {result.metadata['success_rate']:.1%} unter 95%"


# ==============================================================================
# Large File Export Tests
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestLargeFileExportPerformance:
    """Performance-Tests fuer grosse Exporte."""

    async def test_large_document_export(
        self,
        export_benchmark_config,
        mock_export_service,
        large_documents_10
    ):
        """10 grosse Dokumente (je 1MB) exportieren."""
        result = ExportBenchmarkResult("large_documents_10")

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await mock_export_service.batch_export(
                large_documents_10, format="json"
            )
            duration = time.time() - start
            result.add_measurement(duration)

            # Validierung
            assert export_result["processed"] == 10
            file_size_mb = len(data) / 1024 / 1024
            result.metadata["file_size_mb"] = file_size_mb

        result.metadata["documents"] = 10
        result.metadata["text_size_per_doc_kb"] = 1024
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        assert result.mean < export_benchmark_config.TARGETS["large_export_max_seconds"]

    async def test_100mb_export_streaming(
        self,
        export_benchmark_config,
        document_generator
    ):
        """100MB Export sollte effizient sein (keine OOM)."""
        result = ExportBenchmarkResult("export_100mb")
        service = MockExportService()

        # 100 Dokumente a 1MB = ca. 100MB
        large_batch = document_generator.create_batch(100, text_size_kb=1024)

        start = time.time()
        data, content_type, export_result = await service.batch_export(
            large_batch, format="json"
        )
        duration = time.time() - start
        result.add_measurement(duration)

        file_size_mb = len(data) / 1024 / 1024

        result.metadata["documents"] = 100
        result.metadata["file_size_mb"] = file_size_mb
        result.metadata["throughput_mb_per_second"] = file_size_mb / duration
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Export sollte unter 60 Sekunden bleiben
        assert duration < export_benchmark_config.TARGETS["large_export_max_seconds"]
        # Mindestens 1 MB/s Throughput
        assert file_size_mb / duration >= 1.0


# ==============================================================================
# Partial Failure Recovery Tests
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestPartialFailureRecovery:
    """Tests fuer Fehlerbehandlung bei Teilausfaellen."""

    async def test_10_percent_failure_rate(
        self,
        export_benchmark_config,
        document_generator
    ):
        """Bei 10% fehlenden Docs: Export mit Warnings fortsetzen."""
        result = ExportBenchmarkResult("partial_failure_10pct")
        service = MockExportService()

        batch = document_generator.create_batch(100)

        for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
            start = time.time()
            data, content_type, export_result = await service.batch_export(
                batch,
                format="json",
                simulate_failure_rate=0.10  # 10% Fehlerrate
            )
            duration = time.time() - start
            result.add_measurement(duration)

            # Etwa 90% sollten erfolgreich sein
            assert export_result["processed"] >= 80, \
                f"Nur {export_result['processed']} von 100 verarbeitet"

        result.metadata["simulated_failure_rate"] = 0.10
        result.metadata["expected_success_rate"] = 0.90
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

    async def test_recovery_after_errors(
        self,
        export_benchmark_config,
        document_generator
    ):
        """Export sollte nach Fehlern fortfahren."""
        result = ExportBenchmarkResult("error_recovery")
        service = MockExportService()

        batch = document_generator.create_batch(50)

        # Simuliere verschiedene Fehlerraten
        failure_rates = [0.0, 0.05, 0.10, 0.20, 0.30]

        for rate in failure_rates:
            start = time.time()
            data, content_type, export_result = await service.batch_export(
                batch,
                format="json",
                simulate_failure_rate=rate
            )
            duration = time.time() - start

            result.add_measurement(duration)
            result.metadata[f"rate_{int(rate*100)}_processed"] = export_result["processed"]
            result.metadata[f"rate_{int(rate*100)}_failed"] = export_result["failed"]

        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Selbst bei 30% Fehlerrate sollte Export nicht abstuerzen
        assert "rate_30_processed" in result.metadata


# ==============================================================================
# Format Comparison Tests
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestFormatComparison:
    """Vergleich verschiedener Export-Formate."""

    async def test_format_comparison(
        self,
        export_benchmark_config,
        document_generator
    ):
        """Vergleiche Performance verschiedener Formate."""
        result = ExportBenchmarkResult("format_comparison")
        service = MockExportService()

        batch = document_generator.create_batch(100)
        formats = ["json", "csv", "zip"]

        format_results = {}

        for fmt in formats:
            times = []
            sizes = []

            for _ in range(export_benchmark_config.BENCHMARK_ITERATIONS):
                start = time.time()
                data, content_type, export_result = await service.batch_export(
                    batch, format=fmt
                )
                duration = time.time() - start
                times.append(duration)
                sizes.append(len(data))

            format_results[fmt] = {
                "avg_time": statistics.mean(times),
                "avg_size_kb": statistics.mean(sizes) / 1024,
                "min_time": min(times),
                "max_time": max(times)
            }
            result.add_measurement(statistics.mean(times))

        result.metadata["format_results"] = format_results
        result.metadata["fastest_format"] = min(format_results, key=lambda x: format_results[x]["avg_time"])
        result.metadata["smallest_format"] = min(format_results, key=lambda x: format_results[x]["avg_size_kb"])
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)


# ==============================================================================
# Comprehensive Export Benchmark
# ==============================================================================


@pytest.mark.performance
@pytest.mark.asyncio
class TestComprehensiveExportBenchmark:
    """Umfassender Export-Benchmark."""

    async def test_full_export_benchmark_suite(
        self,
        export_benchmark_config,
        document_generator
    ):
        """Fuehre vollstaendige Export-Benchmark-Suite aus."""
        result = ExportBenchmarkResult("comprehensive_export_suite")
        service = MockExportService()

        results = {}

        # 1. Kleine Batches (10, 50, 100)
        for size in [10, 50, 100]:
            batch = document_generator.create_batch(size)
            start = time.time()
            await service.batch_export(batch, format="json")
            results[f"batch_{size}_time"] = time.time() - start

        # 2. Format-Vergleich
        batch = document_generator.create_batch(50)
        for fmt in ["json", "csv", "zip"]:
            start = time.time()
            data, _, _ = await service.batch_export(batch, format=fmt)
            results[f"format_{fmt}_time"] = time.time() - start
            results[f"format_{fmt}_size_kb"] = len(data) / 1024

        # 3. Concurrent Test
        batches = [document_generator.create_batch(20) for _ in range(5)]
        start = time.time()
        tasks = [asyncio.create_task(service.batch_export(b, format="json")) for b in batches]
        await asyncio.gather(*tasks)
        results["concurrent_5x20_time"] = time.time() - start

        # 4. Mit/Ohne Text
        batch = document_generator.create_batch(50)
        start = time.time()
        await service.batch_export(batch, format="json", include_text=True)
        results["with_text_time"] = time.time() - start

        start = time.time()
        await service.batch_export(batch, format="json", include_text=False)
        results["without_text_time"] = time.time() - start

        result.metadata = results
        result.finalize()

        save_export_benchmark_result(result, export_benchmark_config)

        # Zusammenfassung ausgeben
        print("\n" + "=" * 70)
        print("EXPORT PERFORMANCE BENCHMARK ERGEBNISSE")
        print("=" * 70)
        for key, value in sorted(results.items()):
            if "time" in key:
                print(f"  {key}: {value:.3f}s")
            else:
                print(f"  {key}: {value:.2f}")
        print("=" * 70 + "\n")


# ==============================================================================
# Report Generator
# ==============================================================================


@pytest.fixture(scope="session", autouse=True)
def generate_export_report(request):
    """Generiere Export-Benchmark-Report nach allen Tests."""
    yield

    # Nach Tests: Report generieren
    results_dir = ExportBenchmarkConfig.RESULTS_DIR
    if results_dir.exists():
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "test_suite": "export_performance",
            "results": []
        }

        for result_file in results_dir.glob("export_*.json"):
            try:
                with open(result_file, encoding="utf-8") as f:
                    report["results"].append(json.load(f))
            except Exception:
                pass

        if report["results"]:
            report_file = results_dir / f"export_benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            print(f"\nExport Benchmark Report: {report_file}")

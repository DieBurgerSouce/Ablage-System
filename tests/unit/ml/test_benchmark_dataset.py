# -*- coding: utf-8 -*-
"""
Unit tests for Benchmark Dataset Module.

Tests benchmark sample management, validation,
and benchmark report generation.
"""

import pytest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.ml.benchmark_dataset import (
    BenchmarkSample,
    BenchmarkResult,
    BenchmarkReport,
    BenchmarkDataset,
    DocumentType,
    Language,
    Difficulty,
)


@pytest.mark.unit
class TestBenchmarkSample:
    """Test BenchmarkSample dataclass."""

    def test_create_sample(self):
        """Test creating a benchmark sample."""
        sample = BenchmarkSample(
            id="test_001",
            image_path="/path/to/image.png",
            ground_truth_text="Test Text",
            document_type=DocumentType.INVOICE,
            language=Language.DE,  # Korrigiert: GERMAN -> DE
            difficulty=Difficulty.MEDIUM,
            has_fraktur=False,
            expected_umlauts=["ü", "ö"],
        )

        assert sample.id == "test_001"
        assert sample.document_type == DocumentType.INVOICE
        assert sample.language == Language.DE  # Korrigiert: GERMAN -> DE
        assert sample.difficulty == Difficulty.MEDIUM
        assert not sample.has_fraktur
        assert len(sample.expected_umlauts) == 2

    def test_sample_with_metadata(self):
        """Test sample with optional metadata."""
        sample = BenchmarkSample(
            id="test_002",
            image_path="/path/to/image.png",
            ground_truth_text="Rechnung Nr. 12345",
            document_type=DocumentType.INVOICE,
            language=Language.DE,
            difficulty=Difficulty.EASY,
            has_fraktur=False,
            expected_umlauts=[],
            metadata={"source": "manual", "year": 2024},
        )

        assert sample.metadata is not None
        assert sample.metadata["source"] == "manual"


@pytest.mark.unit
class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""

    def test_create_result(self):
        """Test creating a benchmark result."""
        from app.ml.quality_metrics import OCRQualityMetrics

        metrics = OCRQualityMetrics(
            cer=0.05,
            wer=0.1,
            char_accuracy=0.95,
            word_accuracy=0.9,
            levenshtein_distance=2,
            insertions=0,
            deletions=1,
            substitutions=1,
            umlaut_accuracy=1.0
        )

        result = BenchmarkResult(
            sample_id="test_001",
            backend_name="deepseek",
            ocr_output="Test Text",
            metrics=metrics,
            processing_time_ms=150.0,
            success=True,
        )

        assert result.sample_id == "test_001"
        assert result.backend_name == "deepseek"
        assert result.metrics.cer == 0.05
        assert result.success is True

    def test_result_accuracy_check(self):
        """Test result with different metrics."""
        from app.ml.quality_metrics import OCRQualityMetrics

        good_metrics = OCRQualityMetrics(
            cer=0.05,
            wer=0.1,
            char_accuracy=0.95,
            word_accuracy=0.9,
            levenshtein_distance=2,
            insertions=0,
            deletions=1,
            substitutions=1,
            umlaut_accuracy=1.0
        )

        result = BenchmarkResult(
            sample_id="test_001",
            backend_name="deepseek",
            ocr_output="Test",
            metrics=good_metrics,
            processing_time_ms=100.0,
            success=True,
        )

        # Prüfe Metriken
        assert result.metrics.cer < 0.1
        assert result.success


@pytest.mark.unit
class TestBenchmarkReport:
    """Test BenchmarkReport dataclass."""

    def test_create_empty_report(self):
        """Test creating an empty report."""
        report = BenchmarkReport(
            backend_name="deepseek",
            total_samples=0,
            successful_samples=0,
            failed_samples=0,
            avg_cer=0.0,
            avg_wer=0.0,
            avg_umlaut_accuracy=1.0,
            avg_processing_time_ms=0.0,
            min_cer=0.0,
            max_cer=0.0,
            min_wer=0.0,
            max_wer=0.0,
        )

        assert report.total_samples == 0
        assert report.avg_cer == 0.0

    def test_report_with_results(self):
        """Test report with sample results."""
        report = BenchmarkReport(
            backend_name="deepseek",
            total_samples=10,
            successful_samples=9,
            failed_samples=1,
            avg_cer=0.08,
            avg_wer=0.15,
            avg_umlaut_accuracy=0.95,
            avg_processing_time_ms=120.0,
            min_cer=0.02,
            max_cer=0.15,
            min_wer=0.05,
            max_wer=0.25,
        )

        assert report.total_samples == 10
        assert report.backend_name == "deepseek"
        assert report.avg_cer == 0.08


@pytest.mark.unit
class TestBenchmarkDataset:
    """Test BenchmarkDataset class."""

    def setup_method(self):
        """Setup before each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.dataset = BenchmarkDataset(base_path=Path(self.temp_dir))

    def test_add_sample(self):
        """Test adding a sample to dataset."""
        # add_sample nimmt einzelne Parameter
        sample = self.dataset.add_sample(
            image_path="/path/to/image.png",
            ground_truth="Test Text",
            document_type="invoice",
            language="de",
            difficulty="medium",
            has_fraktur=False,
        )

        # Prüfe Sample
        assert sample is not None
        assert sample.ground_truth_text == "Test Text"  # ground_truth_text statt ground_truth
        all_samples = list(self.dataset.get_samples())  # Generator zu Liste
        assert len(all_samples) == 1

    def test_filter_by_type(self):
        """Test filtering samples by document type."""
        # Add samples of different types
        self.dataset.add_sample(
            image_path="/path/1.png",
            ground_truth="Rechnung",
            document_type="invoice",
            language="de",
            difficulty="easy",
        )
        self.dataset.add_sample(
            image_path="/path/2.png",
            ground_truth="Vertrag",
            document_type="contract",
            language="de",
            difficulty="medium",
        )

        # Nutze get_samples mit document_type Filter, Generator zu Liste
        invoices = list(self.dataset.get_samples(document_type="invoice"))

        assert len(invoices) == 1
        assert invoices[0].ground_truth_text == "Rechnung"

    def test_filter_by_difficulty(self):
        """Test filtering samples by difficulty."""
        self.dataset.add_sample(
            image_path="/path/1.png",
            ground_truth="Einfach",
            document_type="letter",
            language="de",
            difficulty="easy",
        )
        self.dataset.add_sample(
            image_path="/path/2.png",
            ground_truth="Schwierig",
            document_type="fraktur",
            language="de",
            difficulty="hard",
            has_fraktur=True,
        )

        # Nutze get_samples mit difficulty Filter, Generator zu Liste
        hard_samples = list(self.dataset.get_samples(difficulty="hard"))

        assert len(hard_samples) == 1
        assert hard_samples[0].has_fraktur

    def test_filter_fraktur_samples(self):
        """Test filtering Fraktur samples."""
        self.dataset.add_sample(
            image_path="/path/1.png",
            ground_truth="Modern",
            document_type="invoice",
            difficulty="easy",
            has_fraktur=False,
        )
        self.dataset.add_sample(
            image_path="/path/2.png",
            ground_truth="Fraktur",
            document_type="fraktur",
            difficulty="hard",
            has_fraktur=True,
        )

        # Nutze get_samples mit has_fraktur Filter, Generator zu Liste
        fraktur_samples = list(self.dataset.get_samples(has_fraktur=True))

        assert len(fraktur_samples) == 1
        assert fraktur_samples[0].has_fraktur is True

    def test_get_sample_not_found(self):
        """Test getting non-existent sample."""
        sample = self.dataset.get_sample("non_existent")
        assert sample is None

    def test_dataset_stats(self):
        """Test getting dataset statistics."""
        # Add multiple samples
        for i in range(5):
            self.dataset.add_sample(
                image_path=f"/path/{i}.png",
                ground_truth=f"Text {i}",
                document_type="invoice" if i < 3 else "contract",
                language="de",
                difficulty="medium",
                has_fraktur=(i == 4),
                expected_umlauts=["ü"] if i % 2 == 0 else None,
            )

        # Nutze get_statistics
        stats = self.dataset.get_statistics()

        assert stats["total_samples"] == 5
        assert "by_type" in stats  # by_type statt by_document_type
        assert "by_difficulty" in stats

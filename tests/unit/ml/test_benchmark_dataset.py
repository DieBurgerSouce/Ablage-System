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
            language=Language.GERMAN,
            difficulty=Difficulty.MEDIUM,
            has_fraktur=False,
            expected_umlauts=["ü", "ö"],
        )

        assert sample.id == "test_001"
        assert sample.document_type == DocumentType.INVOICE
        assert sample.language == Language.GERMAN
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
            language=Language.GERMAN,
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
        result = BenchmarkResult(
            sample_id="test_001",
            backend="deepseek",
            extracted_text="Test Text",
            cer=0.05,
            wer=0.1,
            umlaut_accuracy=1.0,
            processing_time_ms=150.0,
        )

        assert result.sample_id == "test_001"
        assert result.backend == "deepseek"
        assert result.cer == 0.05
        assert result.is_accurate  # CER < 0.1

    def test_result_accuracy_check(self):
        """Test accuracy determination."""
        accurate_result = BenchmarkResult(
            sample_id="test_001",
            backend="deepseek",
            extracted_text="Test",
            cer=0.05,
            wer=0.1,
            umlaut_accuracy=1.0,
            processing_time_ms=100.0,
        )
        assert accurate_result.is_accurate

        inaccurate_result = BenchmarkResult(
            sample_id="test_002",
            backend="surya",
            extracted_text="Tost",
            cer=0.25,
            wer=0.5,
            umlaut_accuracy=0.8,
            processing_time_ms=200.0,
        )
        assert not inaccurate_result.is_accurate


@pytest.mark.unit
class TestBenchmarkReport:
    """Test BenchmarkReport dataclass."""

    def test_create_empty_report(self):
        """Test creating an empty report."""
        report = BenchmarkReport(
            total_samples=0,
            avg_cer=0.0,
            avg_wer=0.0,
            avg_umlaut_accuracy=1.0,
            avg_processing_time_ms=0.0,
            backend_results={},
            document_type_results={},
            difficulty_results={},
        )

        assert report.total_samples == 0
        assert report.avg_cer == 0.0

    def test_report_with_results(self):
        """Test report with backend results."""
        report = BenchmarkReport(
            total_samples=10,
            avg_cer=0.08,
            avg_wer=0.15,
            avg_umlaut_accuracy=0.95,
            avg_processing_time_ms=120.0,
            backend_results={
                "deepseek": {"cer": 0.05, "wer": 0.1, "samples": 5},
                "got_ocr": {"cer": 0.11, "wer": 0.2, "samples": 5},
            },
            document_type_results={},
            difficulty_results={},
        )

        assert report.total_samples == 10
        assert "deepseek" in report.backend_results
        assert report.backend_results["deepseek"]["cer"] == 0.05


@pytest.mark.unit
class TestBenchmarkDataset:
    """Test BenchmarkDataset class."""

    def setup_method(self):
        """Setup before each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.dataset = BenchmarkDataset(data_dir=Path(self.temp_dir))

    def test_add_sample(self):
        """Test adding a sample to dataset."""
        sample = BenchmarkSample(
            id="test_001",
            image_path="/path/to/image.png",
            ground_truth_text="Test Text",
            document_type=DocumentType.INVOICE,
            language=Language.GERMAN,
            difficulty=Difficulty.MEDIUM,
            has_fraktur=False,
            expected_umlauts=[],
        )

        self.dataset.add_sample(sample)

        assert len(self.dataset.samples) == 1
        assert self.dataset.get_sample("test_001") is not None

    def test_filter_by_type(self):
        """Test filtering samples by document type."""
        # Add samples of different types
        self.dataset.add_sample(BenchmarkSample(
            id="invoice_001",
            image_path="/path/1.png",
            ground_truth_text="Rechnung",
            document_type=DocumentType.INVOICE,
            language=Language.GERMAN,
            difficulty=Difficulty.EASY,
            has_fraktur=False,
            expected_umlauts=[],
        ))
        self.dataset.add_sample(BenchmarkSample(
            id="contract_001",
            image_path="/path/2.png",
            ground_truth_text="Vertrag",
            document_type=DocumentType.CONTRACT,
            language=Language.GERMAN,
            difficulty=Difficulty.MEDIUM,
            has_fraktur=False,
            expected_umlauts=[],
        ))

        invoices = self.dataset.filter_by_type(DocumentType.INVOICE)

        assert len(invoices) == 1
        assert invoices[0].id == "invoice_001"

    def test_filter_by_difficulty(self):
        """Test filtering samples by difficulty."""
        self.dataset.add_sample(BenchmarkSample(
            id="easy_001",
            image_path="/path/1.png",
            ground_truth_text="Einfach",
            document_type=DocumentType.LETTER,
            language=Language.GERMAN,
            difficulty=Difficulty.EASY,
            has_fraktur=False,
            expected_umlauts=[],
        ))
        self.dataset.add_sample(BenchmarkSample(
            id="hard_001",
            image_path="/path/2.png",
            ground_truth_text="Schwierig",
            document_type=DocumentType.HISTORICAL,
            language=Language.GERMAN,
            difficulty=Difficulty.HARD,
            has_fraktur=True,
            expected_umlauts=[],
        ))

        hard_samples = self.dataset.filter_by_difficulty(Difficulty.HARD)

        assert len(hard_samples) == 1
        assert hard_samples[0].has_fraktur

    def test_filter_fraktur_samples(self):
        """Test filtering Fraktur samples."""
        self.dataset.add_sample(BenchmarkSample(
            id="modern_001",
            image_path="/path/1.png",
            ground_truth_text="Modern",
            document_type=DocumentType.INVOICE,
            language=Language.GERMAN,
            difficulty=Difficulty.EASY,
            has_fraktur=False,
            expected_umlauts=[],
        ))
        self.dataset.add_sample(BenchmarkSample(
            id="fraktur_001",
            image_path="/path/2.png",
            ground_truth_text="Fraktur",
            document_type=DocumentType.HISTORICAL,
            language=Language.GERMAN,
            difficulty=Difficulty.HARD,
            has_fraktur=True,
            expected_umlauts=[],
        ))

        fraktur_samples = self.dataset.get_fraktur_samples()

        assert len(fraktur_samples) == 1
        assert fraktur_samples[0].id == "fraktur_001"

    def test_get_sample_not_found(self):
        """Test getting non-existent sample."""
        sample = self.dataset.get_sample("non_existent")
        assert sample is None

    def test_dataset_stats(self):
        """Test getting dataset statistics."""
        # Add multiple samples
        for i in range(5):
            self.dataset.add_sample(BenchmarkSample(
                id=f"sample_{i:03d}",
                image_path=f"/path/{i}.png",
                ground_truth_text=f"Text {i}",
                document_type=DocumentType.INVOICE if i < 3 else DocumentType.CONTRACT,
                language=Language.GERMAN,
                difficulty=Difficulty.MEDIUM,
                has_fraktur=i == 4,
                expected_umlauts=["ü"] if i % 2 == 0 else [],
            ))

        stats = self.dataset.get_stats()

        assert stats["total_samples"] == 5
        assert "by_document_type" in stats
        assert "by_difficulty" in stats

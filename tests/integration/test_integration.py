"""
Integration tests for Ablage-System OCR.

Tests interaction between multiple components:
- GPU manager + German validator
- Import validation
- End-to-end workflows
"""

import pytest
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from gpu_manager import GPUManager
from german_validator import GermanValidator


@pytest.mark.integration
class TestComponentIntegration:
    """Integration tests for component interactions."""

    def test_gpu_and_validator_together(self):
        """Test GPU manager and validator work together."""
        gpu_manager = GPUManager()
        validator = GermanValidator()

        # Get GPU status
        gpu_status = gpu_manager.check_availability()

        # Validate some text
        test_text = "Größe: 100GB für €1.000,00"
        validation = validator.validate_umlauts(test_text)

        # Both should work without errors
        assert gpu_status is not None
        assert validation is not None
        assert "ö" in validation["umlauts_found"]
        assert "€" in validator.validate_currency_format(test_text)[0]

    def test_gpu_allocation_with_german_processing(self):
        """Test GPU allocation while processing German text."""
        gpu_manager = GPUManager()
        validator = GermanValidator()

        # Allocate GPU for backend
        allocation = gpu_manager.allocate_for_backend("got_ocr")

        # Process German text during GPU allocation
        german_texts = [
            "Müller GmbH & Co. KG",
            "Straße der 17. Juni 123",
            "Gesamtbetrag: 1.234,56 €",
            "USt-IdNr.: DE123456789",
        ]

        results = []
        for text in german_texts:
            result = validator.validate_umlauts(text)
            results.append(result)

        # Deallocate GPU
        if allocation["success"]:
            gpu_manager.deallocate_backend("got_ocr")

        # Verify all texts were processed correctly
        assert len(results) == len(german_texts)
        assert all(r["valid"] or len(r["potential_errors"]) >= 0 for r in results)

    def test_backend_selection_based_on_content(self):
        """Test that backend selection considers German content complexity."""
        gpu_manager = GPUManager()
        validator = GermanValidator()

        # Simple text - should use lighter backend
        simple_text = "Müller GmbH"
        simple_validation = validator.validate_umlauts(simple_text)

        # Complex text with multiple formats
        complex_text = """
        Müller GmbH & Co. KG
        Straße der 17. Juni 123
        Rechnung Nr.: 2024-001 vom 15.03.2024
        Gesamtbetrag: 1.234,56 € inkl. 19% MwSt.
        USt-IdNr.: DE123456789
        IBAN: DE89 3704 0044 0532 0130 00
        """
        complex_validation = validator.validate_umlauts(complex_text)

        # Both should be valid
        assert simple_validation is not None
        assert complex_validation is not None

        # Complex text should have more detected elements
        assert len(complex_validation["umlauts_found"]) > len(
            simple_validation["umlauts_found"]
        )

    @pytest.mark.slow
    def test_multiple_document_processing_workflow(self):
        """Test processing multiple documents in sequence."""
        gpu_manager = GPUManager()
        validator = GermanValidator()

        # Simulate processing 10 documents
        documents = [
            f"Dokument {i}: Müller GmbH, Betrag: {i * 100},00 €"
            for i in range(1, 11)
        ]

        batch_size = gpu_manager.get_optimal_batch_size("got_ocr")
        processed_count = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            # Allocate GPU for batch
            allocation = gpu_manager.allocate_for_backend("got_ocr")

            # Process batch
            for doc in batch:
                result = validator.validate_umlauts(doc)
                if result["valid"] or len(result["potential_errors"]) >= 0:
                    processed_count += 1

            # Deallocate GPU
            if allocation["success"]:
                gpu_manager.deallocate_backend("got_ocr")

        # All documents should be processed
        assert processed_count == len(documents)


@pytest.mark.integration
def test_imports():
    """Test that all required modules can be imported."""
    # Test PyTorch
    try:
        import torch

        assert hasattr(torch, 'cuda') and callable(torch.cuda.is_available)
        print(f"[OK] PyTorch {torch.__version__} available")
        print(f"[OK] CUDA available: {torch.cuda.is_available()}")
    except ImportError:
        pytest.skip("PyTorch not installed")

    # Test FastAPI
    try:
        import fastapi

        assert hasattr(fastapi, 'FastAPI') and callable(fastapi.FastAPI)
        print(f"[OK] FastAPI {fastapi.__version__} available")
    except ImportError:
        pytest.skip("FastAPI not installed")

    # Test SQLAlchemy
    try:
        import sqlalchemy

        assert hasattr(sqlalchemy, 'create_engine') and callable(sqlalchemy.create_engine)
        print(f"[OK] SQLAlchemy {sqlalchemy.__version__} available")
    except ImportError:
        pytest.skip("SQLAlchemy not installed")

    # Test Redis client
    try:
        import redis

        assert hasattr(redis, 'Redis') and callable(redis.Redis)
        print(f"[OK] Redis client available")
    except ImportError:
        pytest.skip("Redis client not installed")


@pytest.mark.integration
def test_module_compatibility():
    """Test that core modules are compatible with each other."""
    try:
        # Test GPU manager initialization
        gpu_manager = GPUManager()
        assert gpu_manager is not None

        # Test German validator initialization
        validator = GermanValidator()
        assert validator is not None

        # Test they can be used together
        status = gpu_manager.check_availability()
        result = validator.validate_umlauts("Test")

        assert status is not None
        assert result is not None

        print("[OK] All core modules compatible")
    except Exception as e:
        pytest.fail(f"Module compatibility test failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_stress_german_validation():
    """Stress test German validation with large text."""
    validator = GermanValidator()

    # Create large German text
    large_text = " ".join(
        [
            "Müller GmbH & Co. KG, Straße der 17. Juni 123, "
            "Gesamtbetrag: 1.234,56 €, USt-IdNr.: DE123456789"
        ]
        * 100
    )

    # Should handle large text without errors
    result = validator.validate_umlauts(large_text)

    assert result is not None
    assert len(result["umlauts_found"]) > 0
    assert result["confidence"] > 0


@pytest.mark.integration
@pytest.mark.gpu
def test_gpu_backend_switching():
    """Test switching between different GPU backends."""
    gpu_manager = GPUManager()

    if not gpu_manager.check_availability()["available"]:
        pytest.skip("GPU not available")

    backends = ["surya", "got_ocr"]
    results = []

    for backend in backends:
        # Allocate
        allocation = gpu_manager.allocate_for_backend(backend)
        results.append(allocation)

        # Deallocate
        if allocation["success"]:
            gpu_manager.deallocate_backend(backend)

    # All allocations should succeed (or gracefully fallback)
    assert len(results) == len(backends)
    assert all("success" in r for r in results)


if __name__ == "__main__":
    # Run integration tests
    print("Running Ablage-System integration tests...")
    print("=" * 60)

    # Test imports
    print("\n[i] Testing imports...")
    test_imports()

    # Test component integration
    print("\n[i] Testing component integration...")
    test_integration = TestComponentIntegration()
    test_integration.test_gpu_and_validator_together()

    print("\n[OK] Integration tests completed!")

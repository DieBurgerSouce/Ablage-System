"""
DEPRECATED: Tests have been reorganized into unit/ and integration/ directories.

This file is kept for backwards compatibility. Please use the new test structure:

Unit Tests:
- tests/unit/test_gpu_manager.py - GPU resource management tests
- tests/unit/test_german_validator.py - German text validation tests

Integration Tests:
- tests/integration/test_integration.py - Component integration tests

Run all tests:
    pytest                          # All tests
    pytest tests/unit/              # Unit tests only
    pytest tests/integration/       # Integration tests only
    pytest -m unit                  # Tests marked as unit
    pytest -m integration           # Tests marked as integration
    pytest -m gpu                   # Tests requiring GPU

For more information, see tests/conftest.py for shared fixtures.
"""

import sys
from pathlib import Path

# Add app directory to path for backwards compatibility
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

# Import new test structure (for backwards compatibility if someone imports this module)
try:
    from tests.unit.test_gpu_manager import TestGPUManager
    from tests.unit.test_german_validator import TestGermanValidator
    from tests.integration.test_integration import (
        TestComponentIntegration,
        test_imports,
    )

    __all__ = [
        "TestGPUManager",
        "TestGermanValidator",
        "TestComponentIntegration",
        "test_imports",
    ]
except ImportError:
    # If imports fail, provide helpful message
    print(
        "\n⚠️  Tests have been reorganized. Please run:\n"
        "    pytest tests/unit/\n"
        "    pytest tests/integration/\n"
    )
    raise


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("⚠️  NOTICE: Tests have been reorganized")
    print("=" * 70)
    print("\nThis file (test_basic.py) has been deprecated.")
    print("\nPlease use the new test structure:")
    print("  • tests/unit/test_gpu_manager.py")
    print("  • tests/unit/test_german_validator.py")
    print("  • tests/integration/test_integration.py")
    print("\nRun tests with:")
    print("  pytest                    # All tests")
    print("  pytest tests/unit/        # Unit tests")
    print("  pytest tests/integration/ # Integration tests")
    print("=" * 70 + "\n")

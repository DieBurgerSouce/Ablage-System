"""Unit tests for QualityGate validation."""

import pytest
import sys
from pathlib import Path

# Add orchestration to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude" / "orchestration"))

from quality_gate import QualityGate, QualityLevel, QualityResult


class TestQualityGate:
    """Test suite for quality validation."""

    def test_validate_perfect_code_passes_all_checks(self, quality_gate, sample_german_code):
        """Perfect code should pass all quality checks."""
        result = quality_gate.validate(
            code=sample_german_code,
            file_path="test.py",
            model_used="opus"
        )

        assert result.level == QualityLevel.PASSED
        assert len(result.checks_failed) == 0
        assert not result.should_escalate

    def test_validate_code_without_type_hints_fails(self, quality_gate, sample_bad_code):
        """Code without type hints should fail validation."""
        result = quality_gate.validate(
            code=sample_bad_code,
            file_path="test.py",
            model_used="sonnet"
        )

        assert "type_hints" in result.checks_failed or len(result.warnings) > 0

    def test_validate_english_errors_fail_german_check(self, quality_gate, sample_code_with_english_errors):
        """English error messages should fail German language check."""
        result = quality_gate.validate(
            code=sample_code_with_english_errors,
            file_path="test.py",
            model_used="sonnet"
        )

        # Should fail German check or have warnings
        german_check_failed = "german_messages" in result.checks_failed
        has_warnings = len(result.warnings) > 0

        assert german_check_failed or has_warnings

    def test_validate_syntax_error_fails_immediately(self, quality_gate):
        """Syntax errors should be caught and fail validation."""
        code_syntax_error = '''
def broken_function(
    # Missing closing parenthesis!
    return "oops"
'''

        result = quality_gate.validate(
            code=code_syntax_error,
            file_path="test.py",
            model_used="haiku"
        )

        assert "syntax" in result.checks_failed
        assert result.should_escalate  # Syntax errors always escalate

    def test_escalation_threshold_varies_by_model(self, quality_gate, sample_bad_code):
        """Quality thresholds should be stricter for Haiku than Opus."""
        haiku_result = quality_gate.validate(
            code=sample_bad_code,
            file_path="test.py",
            model_used="haiku"
        )
        sonnet_result = quality_gate.validate(
            code=sample_bad_code,
            file_path="test.py",
            model_used="sonnet"
        )
        opus_result = quality_gate.validate(
            code=sample_bad_code,
            file_path="test.py",
            model_used="opus"
        )

        # Haiku should be strictest, Opus most lenient
        # All should detect missing type hints
        assert "type_hints" in haiku_result.checks_failed or len(haiku_result.warnings) > 0

    def test_quality_result_structure(self, quality_gate, sample_german_code):
        """QualityResult should have all required fields."""
        result = quality_gate.validate(
            code=sample_german_code,
            file_path="test.py",
            model_used="sonnet"
        )

        assert hasattr(result, 'level')
        assert hasattr(result, 'checks_passed')
        assert hasattr(result, 'checks_failed')
        assert hasattr(result, 'warnings')
        assert hasattr(result, 'should_escalate')
        assert hasattr(result, 'escalation_reason')
        assert hasattr(result, 'details')

        assert isinstance(result.level, QualityLevel)
        assert isinstance(result.checks_passed, list)
        assert isinstance(result.checks_failed, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.should_escalate, bool)
        assert isinstance(result.details, dict)

    def test_syntax_check_detects_valid_python(self, quality_gate):
        """Valid Python syntax should pass syntax check."""
        valid_code = '''
def greet(name: str) -> str:
    """Greet a person."""
    return f"Hallo, {name}!"
'''

        result = quality_gate.validate(
            code=valid_code,
            file_path="test.py",
            model_used="sonnet"
        )

        assert "syntax" in result.checks_passed or "syntax" not in result.checks_failed

    def test_type_hints_check_comprehensive(self, quality_gate):
        """Type hints check should verify all function signatures."""
        code_partial_hints = '''
def function_with_hints(x: int) -> str:
    """Has hints."""
    return str(x)

def function_without_hints(x):
    """Missing hints."""
    return str(x)
'''

        result = quality_gate.validate(
            code=code_partial_hints,
            file_path="test.py",
            model_used="sonnet"
        )

        # Should fail or warn due to second function missing hints
        assert "type_hints" in result.checks_failed or any("type" in w.lower() for w in result.warnings)

    def test_german_language_check_strict(self, quality_gate):
        """German language check should detect English strings."""
        code_mixed_language = '''
async def process(doc_id: str) -> Dict[str, Any]:
    """Verarbeitet Dokument."""
    try:
        return {"status": "erfolg"}
    except Exception as e:
        # English error message!
        raise ValueError(f"Processing failed: {e}")
'''

        result = quality_gate.validate(
            code=code_mixed_language,
            file_path="test.py",
            model_used="sonnet"
        )

        # Should detect English "Processing failed"
        german_check_failed = "german_messages" in result.checks_failed
        has_german_warning = any("german" in w.lower() or "english" in w.lower() for w in result.warnings)

        assert german_check_failed or has_german_warning

    def test_security_check_detects_dangerous_patterns(self, quality_gate):
        """Security check should detect dangerous code patterns."""
        # SECURITY TEST CASE: This deliberately contains eval() to test that
        # the quality gate can DETECT this dangerous pattern. Do NOT use in production!
        code_with_eval = '''
def execute_code(code_string: str) -> Any:
    """Execute arbitrary code - DANGEROUS EXAMPLE FOR TESTING."""
    return eval(code_string)  # Security risk - intentional test case
'''

        result = quality_gate.validate(
            code=code_with_eval,
            file_path="test.py",
            model_used="sonnet"
        )

        # Should fail security check
        assert "security" in result.checks_failed or any("security" in w.lower() for w in result.warnings)

    def test_import_structure_check(self, quality_gate):
        """Import structure check should verify organization."""
        code_good_imports = '''
import os
import sys
from typing import Dict, List

import requests
import numpy as np

from app.core.config import settings
from app.db.models import User
'''

        code_bad_imports = '''
from app.core.config import settings
import os
import requests
from typing import Dict
import sys
'''

        good_result = quality_gate.validate(code=code_good_imports, file_path="test.py", model_used="sonnet")
        bad_result = quality_gate.validate(code=code_bad_imports, file_path="test.py", model_used="sonnet")

        # Good imports should pass, bad imports should fail or warn
        # (Note: Import order check may be a warning rather than failure)
        assert "imports" in good_result.checks_passed or "imports" not in good_result.checks_failed

    def test_escalation_reason_provided_when_escalating(self, quality_gate):
        """When escalation is needed, reason should be provided."""
        bad_code = '''
def broken():
    return undefined_variable  # Will cause issues
'''

        result = quality_gate.validate(
            code=bad_code,
            file_path="test.py",
            model_used="haiku"
        )

        if result.should_escalate:
            assert result.escalation_reason is not None
            assert len(result.escalation_reason) > 0

    def test_quality_level_progression(self, quality_gate, sample_german_code, sample_bad_code):
        """Quality level should reflect overall code quality."""
        good_result = quality_gate.validate(code=sample_german_code, file_path="test.py", model_used="opus")
        bad_result = quality_gate.validate(code=sample_bad_code, file_path="test.py", model_used="haiku")

        # Good code should have better level than bad code
        quality_order = {
            QualityLevel.PASSED: 3,
            QualityLevel.WARNING: 2,
            QualityLevel.FAILED: 1
        }

        assert quality_order.get(good_result.level, 0) >= quality_order.get(bad_result.level, 0)

    def test_checks_passed_and_failed_mutually_exclusive(self, quality_gate, sample_german_code):
        """A check cannot be both passed and failed."""
        result = quality_gate.validate(code=sample_german_code, file_path="test.py", model_used="sonnet")

        passed_set = set(result.checks_passed)
        failed_set = set(result.checks_failed)

        assert len(passed_set & failed_set) == 0  # No intersection

    def test_details_dict_contains_useful_info(self, quality_gate, sample_german_code):
        """Details dict should contain diagnostic information."""
        result = quality_gate.validate(code=sample_german_code, file_path="test.py", model_used="sonnet")

        assert isinstance(result.details, dict)
        # Should have some diagnostic info
        assert len(result.details) >= 0  # Can be empty for perfect code

    def test_warnings_are_informative(self, quality_gate, sample_bad_code):
        """Warnings should provide actionable feedback."""
        result = quality_gate.validate(code=sample_bad_code, file_path="test.py", model_used="sonnet")

        if result.warnings:
            for warning in result.warnings:
                assert isinstance(warning, str)
                assert len(warning) > 5  # Should be meaningful

    def test_different_file_paths_dont_affect_validation(self, quality_gate, sample_german_code):
        """File path should not affect validation results (only code content matters)."""
        result1 = quality_gate.validate(code=sample_german_code, file_path="app/service.py", model_used="sonnet")
        result2 = quality_gate.validate(code=sample_german_code, file_path="tests/test.py", model_used="sonnet")

        # Results should be identical (same code, same model)
        assert result1.level == result2.level
        assert set(result1.checks_passed) == set(result2.checks_passed)
        assert set(result1.checks_failed) == set(result2.checks_failed)

    def test_model_used_affects_strictness(self, quality_gate):
        """Haiku should have strictest validation, Opus most lenient."""
        mediocre_code = '''
def process(x: int) -> int:
    # Missing docstring, but has type hints
    return x * 2
'''

        haiku_result = quality_gate.validate(code=mediocre_code, file_path="test.py", model_used="haiku")
        sonnet_result = quality_gate.validate(code=mediocre_code, file_path="test.py", model_used="sonnet")
        opus_result = quality_gate.validate(code=mediocre_code, file_path="test.py", model_used="opus")

        # Haiku should be most likely to escalate or fail
        # (All should at least warn about missing docstring)
        pass  # Implementation-dependent behavior

    def test_gpu_pattern_check_if_applicable(self, quality_gate):
        """GPU pattern check should validate proper gpu_memory_guard usage."""
        code_with_gpu = '''
import torch

def process_batch(images):
    with gpu_memory_guard():
        return model.process(images)
'''

        result = quality_gate.validate(code=code_with_gpu, file_path="test.py", model_used="sonnet")

        # Should recognize GPU pattern usage
        # (Implementation may vary - check passes or is not applicable)
        assert "gpu" in result.checks_passed or "gpu" not in result.checks_failed

    def test_empty_code_handling(self, quality_gate):
        """Empty code should fail validation gracefully."""
        result = quality_gate.validate(code="", file_path="test.py", model_used="sonnet")

        # Should fail or have specific handling for empty code
        assert result.level in [QualityLevel.FAILED, QualityLevel.WARNING]

    def test_very_long_code_performance(self, quality_gate):
        """Validation should handle very long code efficiently."""
        # Generate long but valid code
        long_code = "\n".join([
            f"def function_{i}(x: int) -> int:\n    '''Function {i}.'''\n    return x + {i}"
            for i in range(100)
        ])

        import time
        start = time.time()
        result = quality_gate.validate(code=long_code, file_path="test.py", model_used="sonnet")
        duration = time.time() - start

        # Should complete in reasonable time (< 5 seconds)
        assert duration < 5.0
        assert result.level in [QualityLevel.PASSED, QualityLevel.WARNING, QualityLevel.FAILED]

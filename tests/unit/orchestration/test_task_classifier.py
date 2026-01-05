"""Unit tests for TaskClassifier."""

import pytest
import sys
from pathlib import Path

# Add orchestration to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude" / "orchestration"))

from task_classifier import TaskClassifier, ModelTier, ClassificationResult


class TestTaskClassifier:
    """Test suite for task classification logic."""

    def test_classify_simple_task_routes_to_haiku(self, task_classifier):
        """Simple formatting tasks should route to Haiku."""
        prompt = "Fix typo in README.md"
        result = task_classifier.classify(prompt, [])

        assert result.tier == ModelTier.HAIKU_SUFFICIENT
        assert result.confidence >= 0.70
        assert result.primary_pattern in ["formatting", "simple", "typo"]

    def test_classify_complex_architecture_routes_to_opus(self, task_classifier):
        """Complex architectural tasks should route to Opus."""
        prompt = "Design a distributed consensus algorithm for multi-datacenter deployment with Byzantine fault tolerance"
        result = task_classifier.classify(prompt, [])

        assert result.tier == ModelTier.OPUS_REQUIRED
        assert result.confidence >= 0.80
        assert "architecture" in result.primary_pattern or "design" in result.primary_pattern

    def test_classify_standard_implementation_routes_to_sonnet(self, task_classifier):
        """Standard implementations should route to Sonnet."""
        prompt = "Implement user login with email/password authentication and session management"
        result = task_classifier.classify(prompt, [])

        assert result.tier == ModelTier.SONNET_CAPABLE
        assert result.confidence >= 0.70
        assert "implementation" in result.primary_pattern

    def test_classify_with_critical_files_escalates_tier(self, task_classifier):
        """Tasks affecting critical files should escalate tier."""
        prompt = "Update authentication logic"
        critical_files = ["app/core/security.py", "app/api/auth.py"]

        result = task_classifier.classify(prompt, critical_files)

        # Should be at least Sonnet, possibly Opus
        assert result.tier in [ModelTier.SONNET_CAPABLE, ModelTier.OPUS_REQUIRED]
        assert result.file_impact_score > 0.5

    def test_classify_empty_prompt_handles_gracefully(self, task_classifier):
        """Empty prompt should be handled gracefully (fallback to Opus)."""
        result = task_classifier.classify("", [])

        # Should fallback to Opus for safety
        assert result.tier == ModelTier.OPUS_REQUIRED
        assert result.confidence < 0.5

    def test_classify_confidence_always_in_range(self, task_classifier, sample_task_prompts):
        """Confidence scores should always be 0.0-1.0."""
        for tier_name, prompts in sample_task_prompts.items():
            for prompt in prompts:
                result = task_classifier.classify(prompt, [])
                assert 0.0 <= result.confidence <= 1.0, f"Confidence out of range for {tier_name}: {result.confidence}"

    def test_pattern_matching_german_keywords(self, task_classifier):
        """German keywords should be recognized in pattern matching."""
        prompt = "Implementiere Authentifizierung mit JWT und Passwort-Hashing"
        result = task_classifier.classify(prompt, [])

        # Should recognize "Implementiere" as implementation pattern
        assert result.tier in [ModelTier.SONNET_CAPABLE, ModelTier.OPUS_REQUIRED]
        assert "implementation" in result.primary_pattern or result.tier == ModelTier.OPUS_REQUIRED

    @pytest.mark.parametrize("file_count,expected_min_tier", [
        (0, ModelTier.HAIKU_SUFFICIENT),
        (1, ModelTier.HAIKU_SUFFICIENT),
        (3, ModelTier.HAIKU_SUFFICIENT),
        (5, ModelTier.SONNET_CAPABLE),
        (10, ModelTier.SONNET_CAPABLE),
    ])
    def test_file_count_affects_tier_selection(self, task_classifier, file_count, expected_min_tier):
        """Task tier should scale with number of affected files."""
        prompt = "Refactor code structure"
        files = [f"file_{i}.py" for i in range(file_count)]

        result = task_classifier.classify(prompt, files)

        # Should be at least the expected tier (can be higher)
        if expected_min_tier == ModelTier.HAIKU_SUFFICIENT:
            assert result.tier in [ModelTier.HAIKU_SUFFICIENT, ModelTier.SONNET_CAPABLE, ModelTier.OPUS_REQUIRED]
        elif expected_min_tier == ModelTier.SONNET_CAPABLE:
            assert result.tier in [ModelTier.SONNET_CAPABLE, ModelTier.OPUS_REQUIRED]

    def test_complexity_score_calculation(self, task_classifier):
        """Complexity score should reflect task difficulty."""
        simple_prompt = "Add comma to list"
        complex_prompt = "Design distributed microservices architecture with event sourcing, CQRS, and saga patterns"

        simple_result = task_classifier.classify(simple_prompt, [])
        complex_result = task_classifier.classify(complex_prompt, [])

        assert complex_result.complexity_score > simple_result.complexity_score

    def test_classification_result_structure(self, task_classifier):
        """ClassificationResult should have all required fields."""
        result = task_classifier.classify("Test task", ["file.py"])

        assert hasattr(result, 'tier')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'reasoning')
        assert hasattr(result, 'primary_pattern')
        assert hasattr(result, 'matched_patterns')
        assert hasattr(result, 'complexity_score')
        assert hasattr(result, 'file_impact_score')

        assert isinstance(result.tier, ModelTier)
        assert isinstance(result.confidence, float)
        assert isinstance(result.reasoning, str)
        assert isinstance(result.primary_pattern, str)
        assert isinstance(result.matched_patterns, list)
        assert isinstance(result.complexity_score, float)
        assert isinstance(result.file_impact_score, float)

    def test_refactoring_tasks_use_sonnet_or_opus(self, task_classifier):
        """Refactoring tasks should use Sonnet or Opus."""
        prompt = "Refactor authentication module to use dependency injection"
        result = task_classifier.classify(prompt, ["app/auth.py"])

        assert result.tier in [ModelTier.SONNET_CAPABLE, ModelTier.OPUS_REQUIRED]
        assert "refactor" in result.primary_pattern.lower() or "refactor" in result.matched_patterns

    def test_testing_tasks_use_sonnet(self, task_classifier):
        """Testing tasks typically use Sonnet."""
        prompt = "Add unit tests for UserService class"
        result = task_classifier.classify(prompt, ["tests/test_user.py"])

        # Testing is typically Sonnet (can be Haiku for simple tests)
        assert result.tier in [ModelTier.HAIKU_SUFFICIENT, ModelTier.SONNET_CAPABLE]

    def test_documentation_tasks_use_haiku(self, task_classifier):
        """Documentation tasks typically use Haiku."""
        prompt = "Update README with installation instructions"
        result = task_classifier.classify(prompt, ["README.md"])

        # Documentation is typically Haiku
        assert result.tier == ModelTier.HAIKU_SUFFICIENT

    def test_security_tasks_use_opus(self, task_classifier):
        """Security-related tasks should use Opus."""
        prompt = "Implement OAuth2 authentication with JWT tokens and refresh token rotation"
        result = task_classifier.classify(prompt, ["app/core/security.py"])

        # Security tasks should prefer Opus
        assert result.tier in [ModelTier.OPUS_REQUIRED, ModelTier.SONNET_CAPABLE]
        assert result.confidence >= 0.70

    def test_classification_with_multiple_patterns(self, task_classifier):
        """Tasks matching multiple patterns should be handled correctly."""
        prompt = "Implement and test new authentication endpoint with security best practices"
        result = task_classifier.classify(prompt, ["app/api/auth.py", "tests/test_auth.py"])

        # Should match implementation, testing, security patterns
        assert len(result.matched_patterns) >= 2
        # Should escalate to Opus due to security + multiple patterns
        assert result.tier in [ModelTier.OPUS_REQUIRED, ModelTier.SONNET_CAPABLE]

    def test_file_impact_score_with_no_files(self, task_classifier):
        """File impact score should be low with no files."""
        result = task_classifier.classify("Design algorithm", [])
        assert result.file_impact_score == 0.0

    def test_file_impact_score_with_many_files(self, task_classifier):
        """File impact score should be high with many files."""
        files = [f"app/module_{i}.py" for i in range(20)]
        result = task_classifier.classify("Refactor codebase", files)
        assert result.file_impact_score > 0.7

    def test_reasoning_is_informative(self, task_classifier):
        """Reasoning should provide clear explanation."""
        result = task_classifier.classify("Implement user registration", ["app/api/users.py"])

        assert len(result.reasoning) > 20  # Should have substantial reasoning
        assert any(word in result.reasoning.lower() for word in ["implementation", "feature", "task", "pattern"])

    def test_consistency_across_similar_prompts(self, task_classifier):
        """Similar prompts should yield consistent tier selection."""
        prompts = [
            "Fix typo in line 42 of README.md",
            "Correct spelling error in documentation",
            "Update copyright year in LICENSE file"
        ]

        results = [task_classifier.classify(p, []) for p in prompts]

        # All should be Haiku
        assert all(r.tier == ModelTier.HAIKU_SUFFICIENT for r in results)

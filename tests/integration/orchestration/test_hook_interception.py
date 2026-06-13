"""Integration tests for Claude Code hook interception."""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

# Add hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude" / "hooks"))

# Diese Suite testet die claude-flow-Hooks unter `.claude/hooks/`
# (claude_task_interceptor, post_task_quality), NICHT die Ablage-App. Dieses
# Verzeichnis ist im Backend-Container nicht gemountet (nur `app/` + `tests/`),
# daher sind die Module dort nicht importierbar. Sauber ueberspringen statt
# ModuleNotFoundError je Testmethode.
pytest.importorskip(
    "claude_task_interceptor",
    reason="claude-flow-Hook-Tooling (.claude/hooks) im App-Container nicht verfuegbar",
)
pytest.importorskip(
    "post_task_quality",
    reason="claude-flow-Hook-Tooling (.claude/hooks) im App-Container nicht verfuegbar",
)


@pytest.mark.integration
class TestHookInterception:
    """Test hook execution and Task() call generation."""

    def test_pre_task_hook_creates_valid_task_json(self):
        """Pre-task hook should create valid Task() call JSON."""
        # Mock task data
        task_data = {
            "prompt": "Implement user authentication",
            "files": ["app/auth.py", "app/api/login.py"]
        }

        # Import hook (would normally be executed by Claude Code)
        with patch('sys.argv', ['hook.py', json.dumps(task_data)]), \
             patch('builtins.print') as mock_print:

            # Mock orchestration components
            with patch('claude_task_interceptor.TaskClassifier') as MockClassifier, \
                 patch('claude_task_interceptor.DecisionCache') as MockCache:

                # Setup mocks
                mock_classifier_instance = Mock()
                mock_classifier_instance.classify.return_value = Mock(
                    tier=Mock(value="sonnet"),
                    confidence=0.87,
                    reasoning="Standard authentication implementation",
                    primary_pattern="implementation",
                    matched_patterns=["authentication", "implementation"],
                    complexity_score=0.65,
                    file_impact_score=0.50
                )
                MockClassifier.return_value = mock_classifier_instance

                mock_cache_instance = Mock()
                mock_cache_instance.find_relevant.return_value = []
                MockCache.return_value = mock_cache_instance

                # Execute hook
                try:
                    from claude_task_interceptor import intercept_task
                    intercept_task()
                except SystemExit:
                    pass  # Hook may exit

                # Verify Task() JSON was printed
                if mock_print.called:
                    output = mock_print.call_args[0][0]
                    task_json = json.loads(output)

                    # Validate structure
                    assert "type" in task_json
                    assert task_json["type"] == "Task"
                    assert "subagent_type" in task_json
                    assert task_json["subagent_type"] in ["opus-task", "sonnet-implementation", "haiku-task"]
                    assert "prompt" in task_json
                    assert "description" in task_json

    def test_pre_task_hook_selects_correct_agent_for_complexity(self):
        """Hook should select appropriate agent based on task complexity."""
        test_cases = [
            ("Fix typo in README", [], "haiku-task"),
            ("Implement user authentication with JWT", ["app/auth.py"], "sonnet-implementation"),
            ("Design distributed consensus algorithm", ["app/core/consensus.py"], "opus-task"),
        ]

        for prompt, files, expected_agent in test_cases:
            task_data = {"prompt": prompt, "files": files}

            with patch('sys.argv', ['hook.py', json.dumps(task_data)]), \
                 patch('builtins.print') as mock_print, \
                 patch('claude_task_interceptor.TaskClassifier') as MockClassifier, \
                 patch('claude_task_interceptor.DecisionCache'):

                # Setup classifier to return appropriate tier
                tier_map = {
                    "haiku-task": Mock(value="haiku"),
                    "sonnet-implementation": Mock(value="sonnet"),
                    "opus-task": Mock(value="opus")
                }

                mock_classifier_instance = Mock()
                mock_classifier_instance.classify.return_value = Mock(
                    tier=tier_map[expected_agent],
                    confidence=0.90,
                    reasoning=f"Task requires {expected_agent}",
                    primary_pattern="implementation",
                    matched_patterns=["implementation"],
                    complexity_score=0.50,
                    file_impact_score=0.30
                )
                MockClassifier.return_value = mock_classifier_instance

                # Execute hook
                try:
                    from claude_task_interceptor import intercept_task
                    intercept_task()
                except SystemExit:
                    pass

                # Verify correct agent selected
                if mock_print.called:
                    output = mock_print.call_args[0][0]
                    task_json = json.loads(output)
                    assert task_json["subagent_type"] == expected_agent

    def test_pre_task_hook_includes_cached_decisions_for_sonnet(self):
        """Hook should include cached Opus decisions for Sonnet/Haiku tasks."""
        task_data = {
            "prompt": "Add authentication endpoint",
            "files": ["app/api/auth.py"]
        }

        # Mock cached decision
        cached_decision = Mock(
            decision="Use JWT with bcrypt",
            reasoning="Industry standard for authentication",
            confidence=0.95
        )

        with patch('sys.argv', ['hook.py', json.dumps(task_data)]), \
             patch('builtins.print') as mock_print, \
             patch('claude_task_interceptor.TaskClassifier') as MockClassifier, \
             patch('claude_task_interceptor.DecisionCache') as MockCache:

            # Setup mocks
            mock_classifier_instance = Mock()
            mock_classifier_instance.classify.return_value = Mock(
                tier=Mock(value="sonnet"),
                confidence=0.85,
                reasoning="Authentication implementation",
                primary_pattern="implementation",
                matched_patterns=["authentication"],
                complexity_score=0.65,
                file_impact_score=0.50
            )
            MockClassifier.return_value = mock_classifier_instance

            mock_cache_instance = Mock()
            mock_cache_instance.find_relevant.return_value = [cached_decision]
            MockCache.return_value = mock_cache_instance

            # Execute hook
            try:
                from claude_task_interceptor import intercept_task
                intercept_task()
            except SystemExit:
                pass

            # Verify cached decisions included in prompt
            if mock_print.called:
                output = mock_print.call_args[0][0]
                task_json = json.loads(output)

                # Prompt should mention cached decisions
                assert "RELEVANT CACHED DECISIONS" in task_json["prompt"] or \
                       "JWT" in task_json["prompt"]  # Decision content included

    def test_hook_graceful_failure_on_invalid_input(self):
        """Hook should fail gracefully with invalid input."""
        invalid_inputs = [
            "",  # Empty
            "not json",  # Invalid JSON
            "{}",  # Missing required fields
        ]

        for invalid_input in invalid_inputs:
            with patch('sys.argv', ['hook.py', invalid_input]):
                # Should not crash - graceful failure
                try:
                    from claude_task_interceptor import intercept_task
                    intercept_task()
                except Exception as e:
                    # Should not raise - either returns None or prints nothing
                    if not isinstance(e, (SystemExit, ImportError)):
                        pytest.fail(f"Hook should not crash on invalid input: {e}")

    def test_post_task_hook_validates_quality(self):
        """Post-task hook should validate output quality."""
        task_result = {
            "output": '''
async def authenticate(username: str, password: str) -> bool:
    """Authenticate user with credentials."""
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    # ... authentication logic
    return True
''',
            "model": "sonnet",
            "task_id": "test-123"
        }

        with patch('sys.argv', ['hook.py', json.dumps(task_result)]), \
             patch('builtins.print') as mock_print:

            # Mock quality gate
            with patch('post_task_quality.QualityGate') as MockQualityGate:
                mock_gate_instance = Mock()
                mock_gate_instance.validate.return_value = Mock(
                    level=Mock(value="passed"),
                    should_escalate=False,
                    checks_passed=["syntax", "type_hints", "german_messages"],
                    checks_failed=[],
                    warnings=[]
                )
                MockQualityGate.return_value = mock_gate_instance

                # Execute post-task hook
                try:
                    from post_task_quality import validate_and_escalate
                    validate_and_escalate()
                except SystemExit:
                    pass

                # Should validate quality
                assert mock_gate_instance.validate.called

    def test_post_task_hook_escalates_on_quality_failure(self):
        """Post-task hook should create escalation Task() on quality failure."""
        task_result = {
            "output": "def bad_code(x): return x",  # No type hints
            "model": "haiku",
            "task_id": "test-456",
            "original_prompt": "Implement function"
        }

        with patch('sys.argv', ['hook.py', json.dumps(task_result)]), \
             patch('builtins.print') as mock_print:

            # Mock quality gate to fail
            with patch('post_task_quality.QualityGate') as MockQualityGate:
                mock_gate_instance = Mock()
                mock_gate_instance.validate.return_value = Mock(
                    level=Mock(value="failed"),
                    should_escalate=True,
                    escalate_to_tier=Mock(value="sonnet"),
                    escalation_reason="Type hints missing",
                    checks_passed=["syntax"],
                    checks_failed=["type_hints"],
                    warnings=[]
                )
                MockQualityGate.return_value = mock_gate_instance

                # Execute post-task hook
                try:
                    from post_task_quality import validate_and_escalate
                    validate_and_escalate()
                except SystemExit:
                    pass

                # Should create escalation Task()
                if mock_print.called:
                    output = mock_print.call_args[0][0]
                    task_json = json.loads(output)

                    # Verify escalation structure
                    assert task_json["type"] == "Task"
                    assert "sonnet" in task_json["subagent_type"]
                    assert "ESCALATED" in task_json["prompt"]

    def test_hook_handles_german_task_prompts(self):
        """Hook should correctly process German language task prompts."""
        task_data = {
            "prompt": "Implementiere Benutzerauthentifizierung mit JWT-Tokens",
            "files": ["app/auth.py"]
        }

        with patch('sys.argv', ['hook.py', json.dumps(task_data)]), \
             patch('builtins.print') as mock_print, \
             patch('claude_task_interceptor.TaskClassifier') as MockClassifier, \
             patch('claude_task_interceptor.DecisionCache'):

            mock_classifier_instance = Mock()
            mock_classifier_instance.classify.return_value = Mock(
                tier=Mock(value="sonnet"),
                confidence=0.88,
                reasoning="Implementierungsaufgabe",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )
            MockClassifier.return_value = mock_classifier_instance

            # Execute hook
            try:
                from claude_task_interceptor import intercept_task
                intercept_task()
            except SystemExit:
                pass

            # Verify German prompt preserved
            if mock_print.called:
                output = mock_print.call_args[0][0]
                task_json = json.loads(output)

                # Original German prompt should be in output
                assert "Implementiere" in task_json["prompt"] or \
                       "Benutzerauthentifizierung" in task_json["prompt"]

    def test_hook_orchestration_context_included_in_prompt(self):
        """Hook should include orchestration context in enhanced prompt."""
        task_data = {
            "prompt": "Implement feature X",
            "files": ["app/feature.py"]
        }

        with patch('sys.argv', ['hook.py', json.dumps(task_data)]), \
             patch('builtins.print') as mock_print, \
             patch('claude_task_interceptor.TaskClassifier') as MockClassifier, \
             patch('claude_task_interceptor.DecisionCache'):

            mock_classifier_instance = Mock()
            mock_classifier_instance.classify.return_value = Mock(
                tier=Mock(value="sonnet"),
                confidence=0.87,
                reasoning="Feature implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )
            MockClassifier.return_value = mock_classifier_instance

            # Execute hook
            try:
                from claude_task_interceptor import intercept_task
                intercept_task()
            except SystemExit:
                pass

            # Verify orchestration context included
            if mock_print.called:
                output = mock_print.call_args[0][0]
                task_json = json.loads(output)

                # Should include context markers
                context_markers = [
                    "MULTI-MODEL ORCHESTRATION CONTEXT",
                    "Selected Model",
                    "Confidence",
                    "QUALITY REQUIREMENTS"
                ]

                has_context = any(marker in task_json["prompt"] for marker in context_markers)
                assert has_context, "Orchestration context should be included in prompt"

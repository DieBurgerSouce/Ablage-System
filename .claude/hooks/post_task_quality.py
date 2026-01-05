#!/usr/bin/env python3
"""
Post-Task Quality Validation Hook.

Called AFTER task execution to validate quality.
If quality fails, triggers escalation to higher tier.

NO EXTERNAL APIS - Uses Claude Code's native Task() system!

FUNKTIONSWEISE:
1. Claude Code ruft Hook nach Task-Ausführung auf
2. Hook validiert Output-Qualität (6 Checks)
3. Bei Quality-Problemen: Hook gibt Task() JSON für höheres Modell zurück
4. Opus-Entscheidungen werden im Cache gespeichert für Wiederverwendung

QUALITY CHECKS:
- Syntax validation (AST parsing)
- Type hints coverage (100% for function signatures)
- German messages (all user-facing text)
- GPU patterns (memory guards)
- Security (no secrets, no dangerous patterns)
- Import structure (stdlib → third-party → local)
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Setup minimal logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("post_task_quality")

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from task_classifier import TaskClassifier, ModelTier, TIER_TO_AGENT
    from quality_gate import QualityGate
    from decision_cache import DecisionCache
    from learning_feedback import LearningFeedback
    from metrics import OrchestrationMetrics
except ImportError as e:
    logger.warning(f"Orchestration components not available: {e}")
    sys.exit(0)  # Graceful exit


# Escalation mapping
ESCALATION_MAP = {
    ModelTier.HAIKU_SUFFICIENT: ModelTier.SONNET_CAPABLE,
    ModelTier.SONNET_CAPABLE: ModelTier.OPUS_REQUIRED,
    # Opus has no escalation path
}


def validate_and_escalate():
    """
    Validate task output, escalate if quality fails.

    Returns Task() JSON for escalation or success status.
    """
    try:
        # Parse task result from Claude Code
        if len(sys.argv) < 2:
            logger.debug("No task result provided")
            return

        task_result = json.loads(sys.argv[1])

        # Extract task information
        output = task_result.get("output", "")
        model_used = task_result.get("model", "")
        original_prompt = task_result.get("original_prompt", "")
        files = task_result.get("files", [])

        # Determine which tier was used (from model name)
        tier_used = _get_tier_from_model(model_used)

        if not tier_used:
            logger.warning(f"Could not determine tier from model: {model_used}")
            return

        # Initialize quality gate
        quality_gate = QualityGate()

        # Validate quality
        # Use first file path if available, otherwise empty string
        file_path = files[0] if files else ""
        quality_result = quality_gate.validate(
            code=output,
            file_path=file_path,
            model_used=tier_used.value
        )

        # Calculate quality score from checks (QualityResult doesn't have quality_score attribute)
        total_checks = len(quality_result.checks_passed) + len(quality_result.checks_failed)
        quality_score = len(quality_result.checks_passed) / total_checks if total_checks > 0 else 0.0

        logger.info(
            f"Quality validation: score={quality_score:.2f}, "
            f"errors={len(quality_result.checks_failed)}, "
            f"warnings={len(quality_result.warnings)}"
        )

        # Check if escalation needed
        if quality_result.should_escalate and tier_used in ESCALATION_MAP:
            target_tier = ESCALATION_MAP[tier_used]
            agent_name = TIER_TO_AGENT[target_tier]

            logger.warning(
                f"Quality gate failed! Escalating from {tier_used.value} to {target_tier.value}"
            )

            # Record escalation to learning feedback
            try:
                learning = LearningFeedback()
                pattern = _extract_pattern(original_prompt)

                learning.record_task(
                    task_prompt=original_prompt,
                    task_pattern=pattern,
                    initial_tier=tier_used.value,
                    final_tier=target_tier.value,
                    escalated=True,
                    quality_score=quality_score,
                    execution_time_ms=task_result.get("execution_time_ms", 0),
                    success=False  # Failed initial attempt
                )
                logger.info("Escalation recorded to learning feedback")
            except Exception as e:
                logger.warning(f"Failed to record escalation to learning: {e}")

            # Record escalation to metrics
            try:
                metrics = OrchestrationMetrics()
                tokens_used = len(original_prompt + output) // 4
                escalation_path = f"{tier_used.value}->{target_tier.value}"

                metrics.record_task(
                    tier=tier_used.value,
                    tokens_used=tokens_used,
                    quality_score=quality_score,
                    escalated=True,
                    escalation_path=escalation_path,
                    cache_hit=task_result.get("cache_hit", False)
                )
                logger.info("Escalation recorded to metrics")
            except Exception as e:
                logger.warning(f"Failed to record escalation to metrics: {e}")

            # Build escalation prompt
            escalation_prompt = f"""{original_prompt}

---
⬆️ ESCALATION NOTICE:
Previous attempt with {tier_used.value.upper()} failed quality validation.

Quality Issues:
- Score: {quality_score:.2f} / 1.00
- Errors: {len(quality_result.checks_failed)}
- Warnings: {len(quality_result.warnings)}

Critical Problems:
"""
            for error in quality_result.checks_failed[:5]:  # Top 5 errors
                escalation_prompt += f"\n- {error}"

            escalation_prompt += f"""

Please fix these issues and ensure:
- Deutsche Fehlermeldungen für User
- Vollständige Type-Hints
- GPU-Memory unter 85%
- Keine Secrets im Code
"""

            # Create escalation Task() call
            escalation_task = {
                "type": "Task",
                "subagent_type": agent_name,
                "description": f"Escalation to {target_tier.value}",
                "prompt": escalation_prompt
            }

            # Output escalation Task() call
            print(json.dumps(escalation_task))

            # Show user feedback
            print(
                f"\n⬆️  Quality Gate: Escalating to {target_tier.value.upper()}",
                file=sys.stderr
            )
            print(
                f"   Quality Score: {quality_score:.2f} / 1.00",
                file=sys.stderr
            )
            print(
                f"   Errors: {len(quality_result.checks_failed)}",
                file=sys.stderr
            )
            print(
                f"   Warnings: {len(quality_result.warnings)}",
                file=sys.stderr
            )

        else:
            # Quality OK - cache if Opus
            if tier_used == ModelTier.OPUS_REQUIRED:
                try:
                    cache = DecisionCache()
                    cache.store(
                        task_prompt=original_prompt,
                        decision=output,
                        file_paths=files,
                        tier=tier_used.value,
                        confidence=1.0,  # Opus = max confidence
                        reasoning="Opus decision - high quality"
                    )
                    logger.info("Opus decision cached successfully")
                except Exception as e:
                    logger.warning(f"Failed to cache Opus decision: {e}")

            # Record to learning feedback system
            try:
                learning = LearningFeedback()
                # Determine primary pattern from prompt (simple heuristic)
                pattern = _extract_pattern(original_prompt)

                learning.record_task(
                    task_prompt=original_prompt,
                    task_pattern=pattern,
                    initial_tier=tier_used.value,
                    final_tier=tier_used.value,
                    escalated=False,
                    quality_score=quality_score,
                    execution_time_ms=task_result.get("execution_time_ms", 0),
                    success=True
                )
                logger.info("Task recorded to learning feedback")
            except Exception as e:
                logger.warning(f"Failed to record learning feedback: {e}")

            # Record to metrics
            try:
                metrics = OrchestrationMetrics()
                # Estimate tokens (rough heuristic: ~4 chars per token)
                tokens_used = len(original_prompt + output) // 4

                metrics.record_task(
                    tier=tier_used.value,
                    tokens_used=tokens_used,
                    quality_score=quality_score,
                    escalated=False,
                    cache_hit=task_result.get("cache_hit", False)
                )
                logger.info("Task recorded to metrics")
            except Exception as e:
                logger.warning(f"Failed to record metrics: {e}")

            # Output success status
            success_response = {
                "status": "ok",
                "quality_score": quality_score,
                "model": model_used
            }
            print(json.dumps(success_response))

            # Show user feedback
            print(
                f"\n✅ Quality Gate: Passed",
                file=sys.stderr
            )
            print(
                f"   Quality Score: {quality_score:.2f} / 1.00",
                file=sys.stderr
            )
            if quality_result.warnings:
                print(
                    f"   ⚠️  Warnings: {len(quality_result.warnings)}",
                    file=sys.stderr
                )

    except json.JSONDecodeError:
        logger.error("Invalid JSON task result")
    except Exception as e:
        logger.error(f"Quality validation failed: {e}")
        import traceback
        traceback.print_exc()
        # Fail gracefully


def _get_tier_from_model(model_name: str) -> Optional[ModelTier]:
    """
    Determine tier from model name.

    Args:
        model_name: Claude model name (e.g., "claude-opus-4-5-20251101")

    Returns:
        Corresponding ModelTier or None
    """
    model_lower = model_name.lower()

    if "opus" in model_lower:
        return ModelTier.OPUS_REQUIRED
    elif "sonnet" in model_lower:
        return ModelTier.SONNET_CAPABLE
    elif "haiku" in model_lower:
        return ModelTier.HAIKU_SUFFICIENT

    return None


def _extract_pattern(prompt: str) -> str:
    """
    Extract primary task pattern from prompt.

    Args:
        prompt: Task prompt text

    Returns:
        Pattern name (e.g., "implementation", "refactor", "format")
    """
    prompt_lower = prompt.lower()

    # Check for common patterns (same as TaskClassifier)
    if any(word in prompt_lower for word in ["implement", "implementier", "create", "erstell"]):
        return "implementation"
    elif any(word in prompt_lower for word in ["refactor", "umstrukturier"]):
        return "refactor"
    elif any(word in prompt_lower for word in ["test", "pytest"]):
        return "test"
    elif any(word in prompt_lower for word in ["format", "formatier", "sort"]):
        return "format"
    elif any(word in prompt_lower for word in ["fix", "bug", "fehler"]):
        return "bugfix"
    elif any(word in prompt_lower for word in ["security", "sicherheit"]):
        return "security"
    elif any(word in prompt_lower for word in ["architektur", "design"]):
        return "architecture"
    else:
        return "general"


if __name__ == "__main__":
    validate_and_escalate()

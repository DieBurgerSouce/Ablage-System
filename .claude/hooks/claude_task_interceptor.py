#!/usr/bin/env python3
"""
Claude Task Interceptor - Native Claude Code Integration.

This hook intercepts tasks BEFORE execution and returns Task() calls
that route to different agents (Opus/Sonnet/Haiku) based on complexity.

NO EXTERNAL APIS - Uses Claude Code's native Task() system!

FUNKTIONSWEISE:
1. Claude Code ruft Hook vor jeder Task-Ausführung auf
2. Hook klassifiziert Task-Komplexität (Opus/Sonnet/Haiku)
3. Hook gibt Task() JSON zurück → Claude Code führt aus
4. Transparent für User, nutzt normale Claude Code Subscription

INTEGRATION:
- Registriert in .clauderc als pre_task hook
- Gibt Task() call JSON zurück (model via agent YAML frontmatter)
- Graceful Fallback bei Fehlern → normale Ausführung
"""

import sys
import json
import logging
import structlog
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

# Setup structured logging
logger = structlog.get_logger(__name__)

# CRITICAL FIX: Use absolute imports instead of sys.path manipulation
# This prevents ImportError in production
try:
    # Import from absolute path - assumes .claude is in sys.path or PYTHONPATH
    sys.path.insert(0, str(Path(__file__).parent.parent / "orchestration"))
    from task_classifier import TaskClassifier, ModelTier, TIER_TO_AGENT
    from decision_cache import DecisionCache, CachedDecision
    from user_feedback import UserFeedback, DisplayMode
except ImportError as e:
    # Graceful fallback - log error and exit cleanly
    logger.warning("orchestration_import_failed", error=str(e))
    sys.exit(0)  # Claude Code proceeds with normal execution (Opus-only)


def should_intercept_task(task_prompt: str) -> bool:
    """
    Bestimmt ob Task abgefangen werden soll.

    Args:
        task_prompt: Der Task-Prompt

    Returns:
        True wenn Task geroutet werden soll
    """
    # Skip if already a subagent call (prevent recursion)
    if "Task(" in task_prompt or "subagent_type" in task_prompt:
        logger.debug("Skipping subagent call")
        return False

    # Skip system/internal tasks
    system_keywords = ["system", "internal", "debug", "test_"]
    if any(keyword in task_prompt.lower() for keyword in system_keywords):
        logger.debug("Skipping system task")
        return False

    # Must have meaningful content
    if len(task_prompt.strip()) < 20:
        logger.debug("Task too short for orchestration")
        return False

    return True


def create_task_call(
    task_prompt: str,
    tier: ModelTier,
    files: List[str],
    cached_decisions: Optional[List[CachedDecision]] = None
) -> Dict[str, str]:
    """
    Erstellt Task() call JSON für Claude Code.

    Args:
        task_prompt: Original task prompt
        tier: Klassifiziertes Model-Tier
        files: Betroffene Dateien
        cached_decisions: Optional cached Opus decisions

    Returns:
        Task() call als Dictionary
    """
    agent_name = TIER_TO_AGENT[tier]

    # Build enhanced prompt with orchestration context
    enhanced_prompt = task_prompt

    # For Sonnet/Haiku: Add cached Opus decisions
    if cached_decisions:
        enhanced_prompt += "\n\nRELEVANTE CACHED OPUS DECISIONS:\n"
        for decision in cached_decisions[:2]:  # Top 2
            enhanced_prompt += f"- {decision.reasoning[:200]}...\n"

    # Add orchestration metadata
    enhanced_prompt += f"""

---
MULTI-MODEL ORCHESTRATION CONTEXT:
- Selected Model: {tier.value.upper()}
- Files Affected: {len(files)}

QUALITY REQUIREMENTS:
- Deutsche Fehlermeldungen für User
- Vollständige Type-Hints erforderlich
- GPU-Memory unter 85% halten (RTX 4080)
- Keine Secrets im Code
"""

    # Create Task() call
    task_call = {
        "type": "Task",
        "subagent_type": agent_name,
        "description": f"Process with {tier.value}",
        "prompt": enhanced_prompt
    }

    return task_call


def intercept_task():
    """
    Hauptfunktion für Task-Interception.

    Called by Claude Code before task execution.
    Returns Task() call JSON for Claude Code to execute.
    """
    try:
        # Parse task data from Claude Code
        if len(sys.argv) < 2:
            logger.debug("No task data provided")
            return  # No interception needed

        task_data = json.loads(sys.argv[1])

        # Extract task information
        task_prompt = task_data.get("prompt", "")
        files = task_data.get("files", [])

        # Check if we should intercept
        if not should_intercept_task(task_prompt):
            logger.debug("Skipping task interception")
            return

        # Initialize components
        classifier = TaskClassifier()
        cache = DecisionCache()

        # Classify task
        classification = classifier.classify(task_prompt, files)
        tier = classification.tier

        logger.info(
            "task_classified",
            tier=tier.value.upper(),
            confidence=f"{classification.confidence:.0%}"
        )

        # Check cache for Sonnet/Haiku tasks
        cached_decisions = None
        if tier in [ModelTier.SONNET_CAPABLE, ModelTier.HAIKU_SUFFICIENT]:
            try:
                cached_decisions = cache.find_relevant(task_prompt, files)
                if cached_decisions:
                    logger.info("cache_hit", decision_count=len(cached_decisions))
            except Exception as e:
                logger.warning("cache_lookup_failed", error=str(e))

        # Create Task() call
        task_call = create_task_call(task_prompt, tier, files, cached_decisions)

        # Output Task() call as JSON for Claude Code
        print(json.dumps(task_call))

        # Show user feedback using UserFeedback module
        try:
            feedback = UserFeedback(mode=DisplayMode.DETAILED)

            # Estimate tokens (rough heuristic: ~4 chars per token)
            estimated_tokens = len(task_prompt) // 4

            feedback.show_routing_decision(
                model=tier.value,
                confidence=classification.confidence,
                reasoning=classification.reasoning,
                files=len(files),
                estimated_tokens=estimated_tokens,
                cache_hit=cached_decisions is not None and len(cached_decisions) > 0
            )
        except Exception as e:
            # Fallback to simple feedback if UserFeedback fails
            logger.warning("user_feedback_failed", error=str(e))
            print(
                f"\n⚙️ Multi-Model Orchestration:",
                file=sys.stderr
            )
            print(
                f"   Routing zu: {tier.value.upper()}",
                file=sys.stderr
            )
            print(
                f"   Confidence: {classification.confidence:.0%}",
                file=sys.stderr
            )
            print(
                f"   Begründung: {classification.reasoning}",
                file=sys.stderr
            )
            if files:
                print(
                    f"   Dateien: {len(files)}",
                    file=sys.stderr
                )

    except json.JSONDecodeError:
        logger.error("Invalid JSON task data")
        # Graceful fallback - Claude Code proceeds normally
    except Exception as e:
        logger.error("task_interception_failed", error=str(e))
        import traceback
        traceback.print_exc()
        # Fail gracefully - let Claude Code proceed normally


if __name__ == "__main__":
    intercept_task()

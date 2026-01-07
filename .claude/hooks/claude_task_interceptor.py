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

# Add .claude directory to path so we can import orchestration as a package
claude_dir = Path(__file__).parent.parent
sys.path.insert(0, str(claude_dir))

try:
    # Import from orchestration package
    from orchestration import TaskClassifier, ModelTier, ClassificationResult
    from orchestration import DecisionCache, CachedDecision
    from orchestration import UserFeedback, DisplayMode

    # Map tiers to agent names
    TIER_TO_AGENT = {
        ModelTier.OPUS_REQUIRED: "opus-task",
        ModelTier.SONNET_CAPABLE: "sonnet-implementation",
        ModelTier.HAIKU_SUFFICIENT: "haiku-task",
    }
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

    Called by Claude Code as PreToolUse hook (matcher: Task).
    WICHTIG: Claude Code sendet Daten über STDIN als JSON!

    PreToolUse Input Format:
    {
        "session_id": "...",
        "tool_name": "Task",
        "tool_input": {"prompt": "...", "subagent_type": "...", ...}
    }
    """
    try:
        # Read input from stdin (Claude Code sends JSON via stdin)
        input_data = json.load(sys.stdin)

        # Extract tool input from PreToolUse hook data
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Only intercept Task tool calls
        if tool_name != "Task":
            sys.exit(0)

        # Extract task information from tool_input
        task_prompt = tool_input.get("prompt", "")
        subagent_type = tool_input.get("subagent_type", "")
        files: List[str] = []  # PreToolUse doesn't provide files directly

        # Check if we should intercept
        if not should_intercept_task(task_prompt):
            logger.debug("Skipping task interception")
            sys.exit(0)

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

        # For PreToolUse hooks, we output JSON to modify the tool input
        # This allows us to change the subagent_type or model
        modified_input = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                # Add orchestration context to the task
                "modifiedToolInput": {
                    "prompt": task_call["prompt"],
                    "subagent_type": task_call["subagent_type"],
                    "description": task_call["description"],
                    "model": tier.value  # Suggest model tier
                }
            }
        }
        print(json.dumps(modified_input))

        # Show user feedback to stderr (visible in verbose mode)
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
        if cached_decisions:
            print(
                f"   Cache Hit: {len(cached_decisions)} relevante Entscheidungen",
                file=sys.stderr
            )

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON input from stdin", error=str(e))
        # Graceful fallback - let Claude Code proceed normally
        sys.exit(0)
    except Exception as e:
        logger.error("task_interception_failed", error=str(e))
        # Fail gracefully - let Claude Code proceed normally
        sys.exit(0)


if __name__ == "__main__":
    intercept_task()

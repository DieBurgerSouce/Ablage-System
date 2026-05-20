#!/usr/bin/env python3
"""
Automatischer Orchestration Hook für Claude Code.

Dieser Hook wird AUTOMATISCH bei jeder Task-Ausführung aufgerufen
und routet Tasks transparent zwischen Opus, Sonnet und Haiku.

INTEGRATION:
- Wird in .clauderc als pre_task_hook registriert
- Läuft vor jeder Task-Ausführung
- Erstellt echte Subagent-Aufrufe
- Transparent für den User
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto_orchestration")

# Add .claude directory to path so we can import orchestration as a package
claude_dir = Path(__file__).parent.parent
sys.path.insert(0, str(claude_dir))

try:
    # Import from orchestration package (not individual modules)
    from orchestration import TaskClassifier, ClassificationResult, ModelTier
    from orchestration import Orchestrator, OverrideMode
    from orchestration import DecisionCache

    def get_orchestrator() -> Orchestrator:
        """Get or create singleton Orchestrator instance."""
        return Orchestrator()

except ImportError as e:
    logger.warning(f"Orchestration nicht verfügbar: {e}")
    # Graceful fallback - Hook wird übersprungen
    sys.exit(0)


class AutoOrchestrationHook:
    """Automatischer Orchestration Hook für Claude Code."""

    def __init__(self):
        self.orchestrator = Orchestrator()
        self.classifier = TaskClassifier()
        self.cache = DecisionCache()
        self._load_environment_config()

    def _load_environment_config(self) -> None:
        """Lädt Konfiguration aus Environment Variables."""
        # Check if orchestration is disabled
        if os.environ.get("CLAUDE_ORCHESTRATION_DISABLED", "false").lower() == "true":
            logger.info("Orchestration deaktiviert via CLAUDE_ORCHESTRATION_DISABLED")
            sys.exit(0)

        # Load manual override
        override = os.environ.get("CLAUDE_MODEL_OVERRIDE", "auto").lower()
        override_map = {
            "opus": OverrideMode.FORCE_OPUS,
            "sonnet": OverrideMode.FORCE_SONNET,
            "haiku": OverrideMode.FORCE_HAIKU,
            "auto": OverrideMode.AUTO,
        }

        if override in override_map and override != "auto":
            self.orchestrator.set_override(override_map[override])
            logger.info(f"Manual Override aktiv: {override.upper()}")

    def should_intercept_task(self, task_data: Dict[str, Any]) -> bool:
        """
        Entscheidet ob Task abgefangen werden soll.

        Args:
            task_data: Task-Informationen von Claude Code

        Returns:
            True wenn Task geroutet werden soll
        """
        # Skip system/internal tasks
        task_type = task_data.get("type", "")
        if task_type in ["system", "internal", "debug", "hook"]:
            return False

        # Skip if no meaningful prompt
        prompt = task_data.get("prompt", "")
        if not prompt or len(prompt.strip()) < 10:
            return False

        # Skip if already a subagent call
        if "subagent_type" in prompt or "Task(" in prompt:
            return False

        return True

    def extract_context_from_claude(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrahiert Kontext aus Claude Code Environment.

        Args:
            task_data: Task-Daten von Claude Code

        Returns:
            Erweiterte Kontext-Informationen
        """
        context = {
            "workspace_root": os.getcwd(),
            "environment": "claude_code",
            "task_type": task_data.get("type", "unknown"),
            "timestamp": self._get_timestamp(),
        }

        # Extract files from task data
        files = task_data.get("files", [])
        context["affected_files"] = files

        # Add git context if available
        try:
            import subprocess

            # Current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                context["git_branch"] = result.stdout.strip()

            # Changed files
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                changed = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                context["changed_files"] = changed[:10]  # Limit to 10

                # Merge with affected files
                all_files = list(set(files + changed))
                context["affected_files"] = all_files

        except Exception as e:
            logger.debug(f"Git context extraction failed: {e}")
            context["changed_files"] = []

        return context

    def create_subagent_call(
        self,
        classification: ClassificationResult,
        task_data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Erstellt echten Subagent-Aufruf für Claude Code.

        Args:
            classification: Klassifizierungs-Ergebnis
            task_data: Original Task-Daten
            context: Erweiterte Kontext-Informationen

        Returns:
            Subagent-Aufruf als String
        """
        model = classification.tier.value
        subagent_type = f"{model}-task"

        # Build enhanced prompt
        original_prompt = task_data.get("prompt", "")

        enhanced_prompt = f"""ORCHESTRATED TASK ({model.upper()}):

{original_prompt}

ROUTING-INFO:
- Klassifizierung: {classification.reasoning}
- Confidence: {classification.confidence:.0%}
- Betroffene Dateien: {len(context.get('affected_files', []))}

KONTEXT:
- Workspace: {context.get('workspace_root', 'unknown')}
- Git Branch: {context.get('git_branch', 'unknown')}
- Task Type: {context.get('task_type', 'unknown')}

QUALITY-REQUIREMENTS:
- Deutsche Fehlermeldungen
- Vollständige Type-Hints
- GPU-Memory <85% (RTX 4080)
- Multi-Tenant RLS beachten
"""

        # Add cached decisions for Sonnet/Haiku
        if model in ["sonnet", "haiku"]:
            cached = self.cache.find_relevant(
                original_prompt,
                context.get("affected_files", [])
            )
            if cached:
                enhanced_prompt += f"\nRELEVANTE CACHED DECISIONS:\n"
                for decision in cached[:3]:  # Max 3
                    enhanced_prompt += f"- {decision.decision[:100]}...\n"

        # Create Task call
        subagent_call = f"""Task(
    subagent_type="{subagent_type}",
    prompt='''{enhanced_prompt}'''
)"""

        return subagent_call

    def process_task_routing(self, task_data: Dict[str, Any]) -> Optional[str]:
        """
        Hauptfunktion für Task-Routing.

        Args:
            task_data: Task-Daten von Claude Code

        Returns:
            Subagent-Aufruf oder None für Fallback
        """
        try:
            # Extract context
            context = self.extract_context_from_claude(task_data)

            # Classify task
            prompt = task_data.get("prompt", "")
            affected_files = context.get("affected_files", [])

            classification = self.classifier.classify(prompt, affected_files)

            # Log routing decision
            logger.info(
                f"Task routed to {classification.tier.value} "
                f"(confidence: {classification.confidence:.0%})"
            )

            # Show routing info to user (ASCII-safe for Windows)
            print(f"\n[ORCHESTRATION] Multi-Model Routing:", file=sys.stderr)
            print(f"   Routing zu: {classification.tier.value.upper()}", file=sys.stderr)
            print(f"   Confidence: {classification.confidence:.0%}", file=sys.stderr)
            print(f"   Begruendung: {classification.reasoning}", file=sys.stderr)

            if affected_files:
                print(f"   Dateien: {len(affected_files)}", file=sys.stderr)
                for f in affected_files[:3]:
                    print(f"     - {f}", file=sys.stderr)
                if len(affected_files) > 3:
                    print(f"     - ... und {len(affected_files) - 3} weitere", file=sys.stderr)

            # Check if agent exists
            agent_file = Path(f".claude/agents/{classification.tier.value}-task.md")
            if not agent_file.exists():
                print(f"   [WARN] Agent nicht gefunden: {agent_file}", file=sys.stderr)
                print(f"   Erstelle mit: /create-agent {classification.tier.value}-task", file=sys.stderr)
                return None

            # Create subagent call
            subagent_call = self.create_subagent_call(classification, task_data, context)

            print(f"   [OK] Subagent-Aufruf erstellt", file=sys.stderr)

            return subagent_call

        except Exception as e:
            logger.error(f"Task routing failed: {e}")
            print(f"\n[ERROR] Orchestration Fehler: {e}", file=sys.stderr)
            print("   Fallback zu Standard-Verhalten...", file=sys.stderr)
            return None

    def _get_timestamp(self) -> str:
        """Gibt aktuellen Timestamp zurück."""
        from datetime import datetime
        return datetime.now().isoformat()


def main():
    """
    Hauptfunktion für Hook-Integration.

    Wird von Claude Code als UserPromptSubmit Hook aufgerufen.
    WICHTIG: Claude Code sendet Daten über STDIN als JSON!
    """
    try:
        # Read input from stdin (Claude Code sends JSON via stdin)
        input_data = json.load(sys.stdin)

        # Extract prompt from UserPromptSubmit hook data
        # Format: {"session_id": "...", "prompt": "...", "cwd": "...", ...}
        prompt = input_data.get("prompt", "")

        if not prompt or len(prompt.strip()) < 10:
            # Skip short prompts
            sys.exit(0)

        # Convert to task_data format
        task_data = {
            "prompt": prompt,
            "type": "user_prompt",
            "session_id": input_data.get("session_id", ""),
            "cwd": input_data.get("cwd", os.getcwd()),
        }

        # Initialize hook
        hook = AutoOrchestrationHook()

        # Check if task should be intercepted
        if not hook.should_intercept_task(task_data):
            # Skip orchestration for this task
            sys.exit(0)

        # Process task routing
        subagent_call = hook.process_task_routing(task_data)

        if subagent_call:
            # Output routing info as additionalContext for Claude
            # This will be added to Claude's context when processing the user's prompt
            routing_context = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": f"ORCHESTRATION ROUTING: Der folgende Task wurde klassifiziert. "
                                        f"Nutze das passende Model/Agent für optimale Ergebnisse.\n{subagent_call}"
                }
            }
            print(json.dumps(routing_context))

            # Also save to cache for reference
            output_file = Path(".claude/cache/orchestrated_task.txt")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(subagent_call, encoding='utf-8')
        else:
            # No routing needed - exit silently
            sys.exit(0)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input from stdin: {e}")
        # Non-blocking error - let Claude proceed normally
        sys.exit(0)
    except Exception as e:
        logger.error(f"Hook execution failed: {e}")
        # Non-blocking error - let Claude proceed normally
        sys.exit(0)


if __name__ == "__main__":
    main()

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

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from orchestrator import get_orchestrator, OverrideMode
    from task_classifier import TaskClassifier, ClassificationResult
except ImportError as e:
    logger.warning(f"Orchestration nicht verfügbar: {e}")
    # Graceful fallback - Hook wird übersprungen
    sys.exit(0)


class AutoOrchestrationHook:
    """Automatischer Orchestration Hook für Claude Code."""

    def __init__(self):
        self.orchestrator = get_orchestrator()
        self.classifier = TaskClassifier()
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
            cached = self.orchestrator.cache.find_relevant(
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

            # Show routing info to user
            print(f"\n🤖 Multi-Model Orchestration:")
            print(f"   Routing zu: {classification.tier.value.upper()}")
            print(f"   Confidence: {classification.confidence:.0%}")
            print(f"   Begründung: {classification.reasoning}")

            if affected_files:
                print(f"   Dateien: {len(affected_files)}")
                for f in affected_files[:3]:
                    print(f"     • {f}")
                if len(affected_files) > 3:
                    print(f"     • ... und {len(affected_files) - 3} weitere")

            # Check if agent exists
            agent_file = Path(f".claude/agents/{classification.tier.value}-task.md")
            if not agent_file.exists():
                print(f"   ⚠️  Agent nicht gefunden: {agent_file}")
                print(f"   Erstelle mit: /create-agent {classification.tier.value}-task")
                return None

            # Create subagent call
            subagent_call = self.create_subagent_call(classification, task_data, context)

            print(f"   ✅ Subagent-Aufruf erstellt")

            return subagent_call

        except Exception as e:
            logger.error(f"Task routing failed: {e}")
            print(f"\n❌ Orchestration Fehler: {e}")
            print("   Fallback zu Standard-Verhalten...")
            return None

    def _get_timestamp(self) -> str:
        """Gibt aktuellen Timestamp zurück."""
        from datetime import datetime
        return datetime.now().isoformat()


def main():
    """
    Hauptfunktion für Hook-Integration.

    Wird von Claude Code als pre_task_hook aufgerufen.
    """
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("❌ Keine Task-Daten erhalten")
        sys.exit(1)

    try:
        # Parse task data from Claude Code
        task_data_json = sys.argv[1]
        task_data = json.loads(task_data_json)

        # Initialize hook
        hook = AutoOrchestrationHook()

        # Check if task should be intercepted
        if not hook.should_intercept_task(task_data):
            # Skip orchestration for this task
            sys.exit(0)

        # Process task routing
        subagent_call = hook.process_task_routing(task_data)

        if subagent_call:
            # Output subagent call for Claude Code to execute
            print(f"\n📝 ORCHESTRATED TASK:")
            print(subagent_call)

            # Save to file for Claude Code to pick up
            output_file = Path(".claude/cache/orchestrated_task.txt")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(subagent_call, encoding='utf-8')

            print(f"\n💾 Gespeichert in: {output_file}")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid task data JSON: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Hook execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Orchestration Hook für automatisches Multi-Model Routing.

Dieser Hook integriert sich in Claude Code und routet Tasks automatisch
zwischen Opus, Sonnet und Haiku basierend auf Komplexität.

INTEGRATION:
- Wird automatisch bei jeder Task-Ausführung aufgerufen
- Transparent für den User
- Respektiert Manual Overrides
- Koordiniert Ralph Loop Instanzen
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from orchestrator import get_orchestrator, OverrideMode
    from task_classifier import TaskClassifier
except ImportError as e:
    print(f"WARNUNG: Orchestration nicht verfügbar: {e}")
    sys.exit(0)  # Graceful fallback

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestration_hook")


class ClaudeCodeIntegration:
    """Integration mit Claude Code System."""

    def __init__(self):
        self.orchestrator = get_orchestrator()
        self.classifier = TaskClassifier()
        self._load_environment_overrides()

    def _load_environment_overrides(self) -> None:
        """Lädt Manual Overrides aus Environment."""
        override = os.environ.get("CLAUDE_MODEL_OVERRIDE", "auto").lower()

        override_map = {
            "opus": OverrideMode.FORCE_OPUS,
            "sonnet": OverrideMode.FORCE_SONNET,
            "haiku": OverrideMode.FORCE_HAIKU,
            "auto": OverrideMode.AUTO,
        }

        if override in override_map:
            self.orchestrator.set_override(override_map[override])
            if override != "auto":
                logger.info(f"🎛️  Manual Override aktiv: {override.upper()}")

    def should_intercept_task(self, task_data: Dict[str, Any]) -> bool:
        """
        Entscheidet ob Task abgefangen werden soll.

        Args:
            task_data: Task-Informationen

        Returns:
            True wenn Task geroutet werden soll
        """

        # Prüfe auf Opt-out
        if os.environ.get("CLAUDE_ORCHESTRATION_DISABLED", "false").lower() == "true":
            return False

        # Prüfe auf spezielle Task-Types die nicht geroutet werden sollen
        task_type = task_data.get("type", "")
        excluded_types = ["system", "internal", "debug"]

        if task_type in excluded_types:
            return False

        # Prüfe Task-Beschreibung
        task_description = task_data.get("prompt", "")
        if not task_description or len(task_description.strip()) < 10:
            return False

        return True

    def extract_context_from_claude(self) -> Dict[str, Any]:
        """
        Extrahiert Kontext aus Claude Code Environment.

        Returns:
            Kontext-Dictionary
        """
        context = {
            "workspace_root": os.getcwd(),
            "environment": "claude_code",
            "timestamp": self._get_timestamp(),
        }

        # Git-Informationen
        try:
            import subprocess
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                context["git_branch"] = result.stdout.strip()
        except Exception:
            pass

        # Aktuelle Dateien (falls verfügbar)
        try:
            # Versuche geänderte Dateien zu finden
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                changed_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
                context["changed_files"] = changed_files[:10]  # Max 10
        except Exception:
            context["changed_files"] = []

        return context

    def _get_timestamp(self) -> str:
        """Gibt aktuellen Timestamp zurück."""
        from datetime import datetime
        return datetime.now().isoformat()

    def route_task(self, task_data: Dict[str, Any]) -> Optional[str]:
        """
        Routet Task durch Orchestration System.

        Args:
            task_data: Task-Daten von Claude Code

        Returns:
            Gerouteter Output oder None für Fallback
        """

        try:
            # Extrahiere Task-Informationen
            task_description = task_data.get("prompt", "")
            affected_files = task_data.get("files", [])

            # Erweitere mit Git-Kontext
            context = self.extract_context_from_claude()
            if context.get("changed_files"):
                affected_files.extend(context["changed_files"])

            # Entferne Duplikate
            affected_files = list(set(affected_files))

            # Klassifiziere Task
            classification = self.classifier.classify(task_description, affected_files)

            # Zeige Routing-Empfehlung
            print(f"\n🤖 Multi-Model Orchestration:")
            print(f"   Empfohlenes Modell: {classification.tier.value.upper()}")
            print(f"   Confidence: {classification.confidence:.0%}")
            print(f"   Begründung: {classification.reasoning}")

            if affected_files:
                print(f"   Betroffene Dateien: {len(affected_files)}")
                for f in affected_files[:3]:
                    print(f"     • {f}")
                if len(affected_files) > 3:
                    print(f"     • ... und {len(affected_files) - 3} weitere")

            # Führe Task aus
            result = self.orchestrator.process_task(
                task_description=task_description,
                context=context,
                affected_files=affected_files
            )

            # Zeige Ergebnis-Summary
            print(f"\n📊 Ausführung abgeschlossen:")
            print(f"   Modell verwendet: {result.model_used.upper()}")
            print(f"   Tokens: {result.tokens_used}")
            print(f"   Kosten: ${result.cost_estimate:.4f}")
            print(f"   Ausführungszeit: {result.execution_time_ms}ms")

            if result.was_escalated:
                print(f"   ⚠️  Eskaliert: {' → '.join(result.escalation_chain)}")

            if result.cached_decisions_used:
                print(f"   🎯 Cache-Hits: {len(result.cached_decisions_used)}")

            # Quality Gate Status
            if result.quality_result.level.value != "passed":
                print(f"   🔍 Quality: {result.quality_result.level.value}")
                if result.quality_result.warnings:
                    for warning in result.quality_result.warnings[:2]:
                        print(f"     ⚠️  {warning}")

            return result.output

        except Exception as e:
            logger.error(f"Orchestration Fehler: {e}")
            print(f"\n❌ Orchestration Fehler: {e}")
            print("   Fallback zu Standard-Verhalten...")
            return None  # Fallback zu normalem Claude

    def show_cost_report(self) -> None:
        """Zeigt Kosten-Report an."""
        try:
            report_data = self.orchestrator.get_cost_report()

            if "error" in report_data:
                print("\n📊 Noch keine Orchestration-Daten verfügbar.")
                return

            print(f"\n💰 Multi-Model Kosten-Report:")
            print(f"   Tasks gesamt: {report_data['overview']['total_tasks']}")
            print(f"   Eskalationsrate: {report_data['overview']['escalation_rate']}")
            print(f"   Ø Ausführungszeit: {report_data['overview']['avg_execution_time']}")
            print(f"")
            print(f"   Tatsächliche Kosten: {report_data['cost_analysis']['actual_cost']}")
            print(f"   Opus-Only Kosten: {report_data['cost_analysis']['opus_only_cost']}")
            print(f"   💚 Einsparungen: {report_data['cost_analysis']['savings']} ({report_data['cost_analysis']['savings_percent']})")
            print(f"")
            print(f"   Modell-Verteilung:")
            for model, count in report_data['model_distribution'].items():
                print(f"     • {model.capitalize()}: {count}")

        except Exception as e:
            print(f"❌ Fehler beim Laden des Reports: {e}")


def main():
    """Hauptfunktion für Hook-Integration."""

    # Prüfe ob als Hook aufgerufen
    if len(sys.argv) < 2:
        print("🤖 Orchestration Hook - Verwendung:")
        print("   python orchestration_hook.py <command> [args]")
        print("")
        print("   Befehle:")
        print("     route <task_json>     - Routet Task")
        print("     classify <task>       - Klassifiziert Task")
        print("     cost-report          - Zeigt Kosten-Report")
        print("     status               - Zeigt System-Status")
        return

    command = sys.argv[1].lower()
    integration = ClaudeCodeIntegration()

    if command == "route":
        if len(sys.argv) < 3:
            print("❌ Task-Daten erforderlich")
            return

        try:
            task_data = json.loads(sys.argv[2])
            if integration.should_intercept_task(task_data):
                result = integration.route_task(task_data)
                if result:
                    print(f"\n📝 Gerouteter Output:\n{result}")
                else:
                    print("\n🔄 Fallback zu Standard-Verhalten")
            else:
                print("\n⏭️  Task nicht für Routing geeignet")
        except json.JSONDecodeError:
            print("❌ Ungültige Task-Daten (JSON erwartet)")
        except Exception as e:
            print(f"❌ Fehler: {e}")

    elif command == "classify":
        if len(sys.argv) < 3:
            print("❌ Task-Beschreibung erforderlich")
            return

        task = " ".join(sys.argv[2:])
        result = integration.classifier.classify(task)

        print(f"\n🎯 Task-Klassifizierung:")
        print(integration.classifier.get_classification_explanation(result))

    elif command == "cost-report":
        integration.show_cost_report()

    elif command == "status":
        try:
            orchestrator = get_orchestrator()
            print(f"\n🚀 Orchestration System Status:")
            print(f"   Session: {orchestrator._session_id}")
            print(f"   Override: {orchestrator.override_mode.value}")
            print(f"   Ralph Loop: {orchestrator.ralph_coordinator.instance_id}")

            # Cache Status
            cache_stats = orchestrator.cache.get_stats()
            print(f"   Cache: {cache_stats['total_entries']} Einträge, {cache_stats['hit_rate']} Hit-Rate")

        except Exception as e:
            print(f"❌ Status-Fehler: {e}")

    else:
        print(f"❌ Unbekannter Befehl: {command}")


if __name__ == "__main__":
    main()

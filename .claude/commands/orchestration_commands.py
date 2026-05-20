#!/usr/bin/env python3
"""
Custom Commands für Multi-Model Orchestration.

Implementiert Claude Code Commands für Manual Override und Monitoring:
- /force-opus, /force-sonnet, /force-haiku, /auto
- /cost-report, /orchestration-status, /cache-stats
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from orchestrator import get_orchestrator, OverrideMode
    from decision_cache import DecisionCache
except ImportError as e:
    print(f"❌ Orchestration nicht verfügbar: {e}")
    sys.exit(1)


class OrchestrationCommands:
    """Custom Commands für Orchestration System."""

    def __init__(self):
        self.orchestrator = get_orchestrator()
        self.cache = DecisionCache()

    def force_opus(self) -> str:
        """Erzwingt Opus für nächste Task."""
        self.orchestrator.set_override(OverrideMode.FORCE_OPUS)
        return """
🧠 **Opus-Modus aktiviert**

Die nächste Task wird mit **Claude Opus** ausgeführt, unabhängig von der automatischen Klassifizierung.

**Verwendung:**
- Für komplexe Architektur-Entscheidungen
- Bei sicherheitskritischen Änderungen
- Wenn höchste Qualität erforderlich ist

**Hinweis:** Override wird nach einer Task automatisch zurückgesetzt.
"""

    def force_sonnet(self) -> str:
        """Erzwingt Sonnet für nächste Task."""
        self.orchestrator.set_override(OverrideMode.FORCE_SONNET)
        return """
⚙️ **Sonnet-Modus aktiviert**

Die nächste Task wird mit **Claude Sonnet** ausgeführt, unabhängig von der automatischen Klassifizierung.

**Verwendung:**
- Für Implementierungs-Tasks
- Test-Generierung
- Dokumentation schreiben
- Code-Reviews

**Hinweis:** Override wird nach einer Task automatisch zurückgesetzt.
"""

    def force_haiku(self) -> str:
        """Erzwingt Haiku für nächste Task."""
        self.orchestrator.set_override(OverrideMode.FORCE_HAIKU)
        return """
✨ **Haiku-Modus aktiviert**

Die nächste Task wird mit **Claude Haiku** ausgeführt, unabhängig von der automatischen Klassifizierung.

**Verwendung:**
- Code-Formatierung
- Import-Sortierung
- Boilerplate-Generierung
- Einfache Transformationen

**⚠️ Warnung:** Haiku ist nur für einfache Tasks geeignet. Bei Problemen erfolgt automatische Eskalation.
"""

    def auto_mode(self) -> str:
        """Aktiviert automatisches Routing."""
        self.orchestrator.set_override(OverrideMode.AUTO)
        return """
🤖 **Automatisches Routing aktiviert**

Das System wählt automatisch das optimale Modell basierend auf:

**Klassifizierungs-Kriterien:**
- Task-Komplexität (Pattern-Matching)
- Betroffene Dateipfade (kritische Pfade → Opus)
- Multi-File Operationen (>5 Dateien → Opus)
- Confidence-Level (<70% → Opus)

**Modell-Verteilung:**
- 🧠 **Opus**: Architektur, Security, GPU-kritisch
- ⚙️ **Sonnet**: Implementierung, Tests, Dokumentation
- ✨ **Haiku**: Formatierung, Boilerplate, einfache Tasks
"""

    def cost_report(self) -> str:
        """Zeigt detaillierten Kosten-Report."""
        try:
            report_data = self.orchestrator.get_cost_report()

            if "error" in report_data:
                return """
📊 **Kosten-Report**

Noch keine Orchestration-Daten in dieser Session verfügbar.

**Erste Schritte:**
1. Führe einige Tasks aus
2. Das System sammelt automatisch Metriken
3. Rufe `/cost-report` erneut auf

**Tipp:** Nutze verschiedene Task-Typen um die Kosten-Optimierung zu sehen.
"""

            overview = report_data['overview']
            cost_analysis = report_data['cost_analysis']
            model_dist = report_data['model_distribution']
            cache_perf = report_data['cache_performance']

            return f"""
💰 **Multi-Model Kosten-Report**

## 📊 Übersicht
- **Tasks gesamt:** {overview['total_tasks']}
- **Eskalationsrate:** {overview['escalation_rate']} (Ziel: <10%)
- **Quality-Failure-Rate:** {overview['quality_failure_rate']} (Ziel: <5%)
- **Ø Ausführungszeit:** {overview['avg_execution_time']}

## 💸 Kosten-Analyse
- **Tatsächliche Kosten:** {cost_analysis['actual_cost']}
- **Opus-Only Kosten:** {cost_analysis['opus_only_cost']}
- **💚 Einsparungen:** {cost_analysis['savings']} ({cost_analysis['savings_percent']})

## 🤖 Modell-Verteilung
- **🧠 Opus:** {model_dist['opus']} Tasks
- **⚙️ Sonnet:** {model_dist['sonnet']} Tasks
- **✨ Haiku:** {model_dist['haiku']} Tasks

## 🎯 Cache-Performance
- **Cache-Hits:** {cache_perf['hits']}
- **Hit-Rate:** {cache_perf['hit_rate']} (Ziel: >30%)

---
**Interpretation:**
- Einsparungen >40%: 🎉 Excellent
- Eskalationsrate <10%: ✅ Optimal
- Cache-Hit-Rate >30%: 🚀 Effizient
"""

        except Exception as e:
            return f"""
❌ **Fehler beim Laden des Kosten-Reports**

```
{str(e)}
```

**Troubleshooting:**
1. Prüfe ob Orchestration-System läuft
2. Überprüfe Dateiberechtigungen in `.claude/cache/`
3. Führe `python .claude/hooks/orchestration_hook.py status` aus
"""

    def orchestration_status(self) -> str:
        """Zeigt System-Status und Metriken."""
        try:
            # System-Info
            session_id = self.orchestrator._session_id
            override_mode = self.orchestrator.override_mode.value
            ralph_instance = self.orchestrator.ralph_coordinator.instance_id

            # Cache-Stats
            cache_stats = self.cache.get_stats()

            # Environment-Check
            env_disabled = os.environ.get("CLAUDE_ORCHESTRATION_DISABLED", "false")
            env_override = os.environ.get("CLAUDE_MODEL_OVERRIDE", "auto")
            env_debug = os.environ.get("CLAUDE_ORCHESTRATION_DEBUG", "false")

            return f"""
🚀 **Orchestration System Status**

## 🔧 System-Info
- **Session ID:** `{session_id}`
- **Override-Modus:** {override_mode.upper()}
- **Ralph Loop ID:** `{ralph_instance}`

## 💾 Decision Cache
- **Einträge:** {cache_stats['total_entries']}
- **Hit-Rate:** {cache_stats['hit_rate']}
- **Cache-Größe:** {cache_stats['cache_size_mb']:.2f} MB
- **Ältester Eintrag:** {cache_stats.get('oldest_entry', 'N/A')}

## 🌍 Environment
- **Orchestration:** {'❌ DEAKTIVIERT' if env_disabled.lower() == 'true' else '✅ AKTIV'}
- **Model Override:** {env_override.upper()}
- **Debug-Modus:** {'✅ AN' if env_debug.lower() == 'true' else '❌ AUS'}

## 📈 Modell-Statistiken
{self._format_model_stats(cache_stats.get('by_model', {}))}

## 🔍 Gesundheits-Check
{self._health_check()}

---
**Befehle:**
- `/force-opus`, `/force-sonnet`, `/force-haiku` - Manual Override
- `/auto` - Automatisches Routing
- `/cost-report` - Detaillierte Kosten-Analyse
- `/cache-stats` - Cache-Details
"""

        except Exception as e:
            return f"""
❌ **Status-Fehler**

```
{str(e)}
```

**Mögliche Ursachen:**
1. Orchestration-System nicht initialisiert
2. Dateiberechtigungen in `.claude/cache/`
3. Korrupte Cache-Dateien

**Lösung:** Führe `python .claude/orchestration/test_components.py` aus
"""

    def cache_stats(self) -> str:
        """Zeigt detaillierte Cache-Statistiken."""
        try:
            stats = self.cache.get_stats()

            return f"""
🎯 **Decision Cache Statistiken**

## 📊 Übersicht
- **Gesamt-Einträge:** {stats['total_entries']}
- **Gespeicherte Entscheidungen:** {stats['total_stores']}
- **Cache-Hits:** {stats['total_hits']}
- **Cache-Misses:** {stats['total_misses']}
- **Hit-Rate:** {stats['hit_rate']}

## 🤖 Nach Modell
{self._format_model_stats(stats.get('by_model', {}))}

## 📈 Performance
- **Durchschnittliche Confidence:** {stats['avg_confidence']:.1%}
- **Cache-Größe:** {stats['cache_size_mb']:.2f} MB
- **Ältester Eintrag:** {stats.get('oldest_entry', 'N/A')}

## 🔧 Cache-Management

**Cache leeren:**
```python
from claude.orchestration import DecisionCache
DecisionCache().clear()
```

**Expired Entries entfernen:**
```python
from claude.orchestration import DecisionCache
DecisionCache()._cleanup_expired()
```

**Für spezifische Dateien invalidieren:**
```python
from claude.orchestration import DecisionCache
DecisionCache().invalidate_for_files(["app/core/auth.py"])
```

---
**Interpretation:**
- Hit-Rate >30%: 🚀 Excellent
- Hit-Rate 10-30%: ✅ Good
- Hit-Rate <10%: ⚠️ Needs Optimization
"""

        except Exception as e:
            return f"""
❌ **Cache-Stats Fehler**

```
{str(e)}
```

**Troubleshooting:**
1. Prüfe `.claude/cache/decisions.json`
2. Überprüfe Dateiberechtigungen
3. Cache neu initialisieren: `DecisionCache().clear()`
"""

    def _format_model_stats(self, by_model: Dict[str, int]) -> str:
        """Formatiert Modell-Statistiken."""
        if not by_model:
            return "- Keine Daten verfügbar"

        total = sum(by_model.values())
        lines = []

        for model, count in by_model.items():
            percentage = (count / total * 100) if total > 0 else 0
            icon = {"opus": "🧠", "sonnet": "⚙️", "haiku": "✨"}.get(model, "🤖")
            lines.append(f"- **{icon} {model.capitalize()}:** {count} ({percentage:.1f}%)")

        return "\n".join(lines)

    def _health_check(self) -> str:
        """Führt Gesundheits-Check durch."""
        checks = []

        # Cache-Dateien prüfen
        cache_dir = Path(".claude/cache")
        if cache_dir.exists():
            checks.append("✅ Cache-Verzeichnis vorhanden")
        else:
            checks.append("❌ Cache-Verzeichnis fehlt")

        # Orchestration-Module prüfen
        try:
            from task_classifier import TaskClassifier
            checks.append("✅ TaskClassifier verfügbar")
        except ImportError:
            checks.append("❌ TaskClassifier nicht verfügbar")

        # Metriken-Datei prüfen
        metrics_file = Path(".claude/cache/metrics.json")
        if metrics_file.exists():
            checks.append("✅ Metriken-Datei vorhanden")
        else:
            checks.append("⚠️ Metriken-Datei fehlt (wird bei erster Task erstellt)")

        return "\n".join(checks)


def main():
    """Hauptfunktion für Command-Ausführung."""
    if len(sys.argv) < 2:
        print("❌ Command erforderlich")
        return

    command = sys.argv[1].lower().replace("/", "").replace("-", "_")
    commands = OrchestrationCommands()

    # Command-Mapping
    command_map = {
        "force_opus": commands.force_opus,
        "force_sonnet": commands.force_sonnet,
        "force_haiku": commands.force_haiku,
        "auto": commands.auto_mode,
        "cost_report": commands.cost_report,
        "orchestration_status": commands.orchestration_status,
        "cache_stats": commands.cache_stats,
    }

    if command in command_map:
        try:
            result = command_map[command]()
            print(result)
        except Exception as e:
            print(f"❌ Command-Fehler: {e}")
    else:
        print(f"❌ Unbekannter Command: {command}")
        print("\nVerfügbare Commands:")
        for cmd in command_map.keys():
            print(f"  /{cmd.replace('_', '-')}")


if __name__ == "__main__":
    main()

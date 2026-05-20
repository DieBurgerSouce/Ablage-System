#!/usr/bin/env python3
"""
/cost-report Command für Claude Code.
Zeigt detaillierte Kosten-Analyse des Orchestration Systems.
"""

import sys
from pathlib import Path

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    report = orchestrator.get_cost_report()

    if "error" in report:
        print("📊 Noch keine Orchestration-Daten verfügbar")
        print("   Führe einige Tasks aus um Daten zu sammeln")
        exit(0)

    print("💰 Multi-Model Kosten-Report")
    print("=" * 50)

    # Overview
    overview = report['overview']
    print(f"📈 Übersicht:")
    print(f"   Tasks gesamt: {overview['total_tasks']}")
    print(f"   Eskalationsrate: {overview['escalation_rate']}")
    print(f"   Quality-Failure-Rate: {overview['quality_failure_rate']}")
    print(f"   Ø Ausführungszeit: {overview['avg_execution_time']}")

    # Cost Analysis
    cost = report['cost_analysis']
    print(f"\n💸 Kosten-Analyse:")
    print(f"   Tatsächliche Kosten: {cost['actual_cost']}")
    print(f"   Opus-Only Kosten: {cost['opus_only_cost']}")
    print(f"   💚 Einsparungen: {cost['savings']} ({cost['savings_percent']})")

    # Model Distribution
    models = report['model_distribution']
    print(f"\n🤖 Modell-Verteilung:")
    for model, count in models.items():
        print(f"   {model.capitalize()}: {count} Tasks")

    # Cache Performance
    cache = report['cache_performance']
    print(f"\n🎯 Cache-Performance:")
    print(f"   Cache-Hits: {cache['hits']}")
    print(f"   Hit-Rate: {cache['hit_rate']}")

except ImportError as e:
    print(f"❌ Orchestration System nicht verfügbar: {e}")
    print("   Führe 'make setup-orchestration' aus")
except Exception as e:
    print(f"❌ Fehler beim Laden des Reports: {e}")

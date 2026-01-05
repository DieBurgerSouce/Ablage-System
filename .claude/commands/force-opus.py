#!/usr/bin/env python3
"""
/force-opus Command für Claude Code.
Erzwingt Opus-Modell für die nächste Task.
"""

import sys
from pathlib import Path

# Add orchestration to path
orchestration_path = Path(__file__).parent.parent / "orchestration"
sys.path.insert(0, str(orchestration_path))

try:
    from orchestrator import get_orchestrator, OverrideMode

    orchestrator = get_orchestrator()
    orchestrator.set_override(OverrideMode.FORCE_OPUS)

    print("🧠 Opus-Modus aktiviert")
    print("   Nächste Task wird mit Opus ausgeführt")
    print("   Automatisches Routing danach wieder aktiv")

except ImportError as e:
    print(f"❌ Orchestration System nicht verfügbar: {e}")
    print("   Führe 'make setup-orchestration' aus")

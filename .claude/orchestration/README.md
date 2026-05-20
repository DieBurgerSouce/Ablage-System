# Multi-Model Orchestration System

Intelligentes Routing zwischen Claude-Modellen für optimale Kosten-Qualitäts-Balance.

## Übersicht

Das System nutzt drei Claude-Modelle strategisch:
- **Opus**: Architekt für komplexe Entscheidungen, Security, GPU-kritische Aufgaben
- **Sonnet**: Ingenieur für Implementierung, Tests, Dokumentation
- **Haiku**: Assistent für Formatierung, Boilerplate, einfache Validierung

## Komponenten

### TaskClassifier
Klassifiziert Aufgaben automatisch basierend auf:
- Pattern-Matching in Task-Beschreibung
- Betroffene Dateipfade (kritische Pfade → Opus)
- Multi-File Operationen (>5 Dateien → Opus)

```python
from claude.orchestration import TaskClassifier

classifier = TaskClassifier()
result = classifier.classify("Implementiere User API", ["app/api/users.py"])
print(f"Empfohlen: {result.tier.value} (Confidence: {result.confidence:.0%})")
```

### ContextCompressor
Komprimiert Kontext für verschiedene Modelle:
- **Opus**: Vollständiger Kontext (nur Secrets gefiltert)
- **Sonnet**: Relevanter Kontext mit Patterns und Standards
- **Haiku**: Minimaler Kontext mit Anweisungen und Beispielen

```python
from claude.orchestration import ContextCompressor

compressor = ContextCompressor()
compressed = compressor.compress(full_context, "sonnet", "implementation")
print(f"Komprimiert: {compressed.compression_ratio:.0%} ({compressed.token_estimate} Tokens)")
```

### DecisionCache
Cached Opus-Entscheidungen für Wiederverwendung:
- Persistente JSON-Speicherung
- Relevanz-Suche basierend auf Patterns und Dateien
- Automatische Expiration (7 Tage TTL)
- Cache-Invalidierung bei Datei-Änderungen

```python
from claude.orchestration import DecisionCache

cache = DecisionCache()

# Speichern
hash_id = cache.store(
    task_description="User Authentication implementieren",
    decision="FastAPI-Users mit JWT verwenden",
    reasoning="Bewährte Lösung mit guter Security",
    affected_patterns=["auth", "jwt"],
    affected_files=["app/auth/"]
)

# Suchen
relevant = cache.find_relevant("Login System implementieren", ["app/auth/login.py"])
```

### QualityGate
Validiert Subagent-Output und entscheidet über Eskalation:
- **Type-Hints**: Prüft Python-Funktionen auf vollständige Typisierung
- **Deutsche Nachrichten**: Erkennt englische User-Facing Strings
- **GPU-Patterns**: Validiert gpu_memory_guard Nutzung
- **Security**: Erkennt gefährliche Patterns (eval, shell=True, etc.)
- **Imports**: Prüft Import-Sortierung und -Struktur

```python
from claude.orchestration import QualityGate

gate = QualityGate()
result = gate.validate(code, "app/service.py", "sonnet")

if result.should_escalate:
    print(f"Eskalation erforderlich: {result.escalation_reason}")
```

## Installation & Setup

1. **Verzeichnisse erstellen:**
```bash
mkdir -p .claude/orchestration .claude/cache
```

2. **Dependencies installieren:**
```bash
pip install -r requirements.txt
```

3. **Tests ausführen:**
```bash
cd .claude/orchestration
python test_components.py
```

## Konfiguration

### Kritische Pfade (immer Opus)
- `app/core/` - Kern-Logik
- `app/security/` - Sicherheits-Code
- `app/agents/ocr/` - OCR-Agenten
- `alembic/versions/` - DB-Migrationen

### Pattern-Beispiele

**Opus-Patterns:**
- "architektur", "security", "gpu management"
- "deepseek", "got-ocr", "multi-tenant"
- "trade-off", "design decision"

**Sonnet-Patterns:**
- "implementier", "test generat", "api endpoint"
- "service layer", "pydantic schema", "fastapi"

**Haiku-Patterns:**
- "formatier", "import sort", "type hint"
- "boilerplate", "mechanisch", "trivial"

## Cache-Management

### Statistiken anzeigen
```python
cache = DecisionCache()
stats = cache.get_stats()
print(f"Einträge: {stats['total_entries']}, Hit-Rate: {stats['hit_rate']}")
```

### Cache leeren
```python
cache.clear()  # Komplett leeren
cache.invalidate_for_files(["app/core/auth.py"])  # Für spezifische Dateien
```

## Quality Gates konfigurieren

### Eskalations-Regeln
- **Haiku**: Jede Warnung führt zur Eskalation
- **Sonnet**: Nur Fehler führen zur Eskalation
- **Kritische Pfade**: Warnungen führen zur Eskalation
- **Multi-File**: >5 Dateien → automatisch Opus

### Custom Checks hinzufügen
```python
def custom_check(code: str, path: str, context: dict) -> dict:
    if "TODO" in code:
        return {"name": "todos", "status": "warning", "message": "TODOs gefunden"}
    return {"name": "todos", "status": "passed"}

gate = QualityGate()
gate.checks.append(custom_check)
```

## Monitoring

### Token-Tracking
Das System schätzt Token-Verbrauch und berechnet Kosten:
- Opus: ~$30/1M Tokens
- Sonnet: ~$7.5/1M Tokens
- Haiku: ~$1/1M Tokens

### Erfolgsmetriken
- **Eskalationsrate**: < 10% (Ziel)
- **Cache-Hit-Rate**: > 30% (Ziel)
- **Kosteneinsparung**: 40-60% vs. reinem Opus

## Troubleshooting

### Häufige Probleme

**1. Falsche Klassifizierung**
```python
# Debug-Info anzeigen
result = classifier.classify(task, files)
print(classifier.get_classification_explanation(result))
```

**2. Cache-Misses**
```python
# Relevante Entscheidungen prüfen
relevant = cache.find_relevant(task, files, min_confidence=0.5)
print(f"Gefunden: {len(relevant)} Entscheidungen")
```

**3. Quality Gate zu strikt**
```python
# Detaillierte Validierung
result = gate.validate(code, path, model)
print(gate.get_quality_report(result))
```

### Logs aktivieren
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestration")
```

## Nächste Schritte

Phase 1 ✅ **Core Infrastructure** (abgeschlossen)
- TaskClassifier, ContextCompressor, DecisionCache, QualityGate

Phase 2 🚧 **Orchestrator & Integration**
- Hauptkomponente, Hooks, Steering Files, Commands

Phase 3 📋 **Skills & Agent Integration**
- Orchestration Skills, Agent Templates, Plugin-Erweiterung

Phase 4 📊 **Testing & Monitoring**
- E2E Tests, Performance Tests, Dokumentation, Dashboards

## Support

Bei Problemen oder Fragen:
1. Tests ausführen: `python test_components.py`
2. Logs prüfen: `.claude/cache/` Verzeichnis
3. Cache-Stats anzeigen: `cache.get_stats()`
4. Issue im Repository erstellen

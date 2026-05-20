---
name: auto-swarm
description: Automatisches Spawnen von Multi-Agent Swarms basierend auf Task-Komplexitaet
version: 1.0.0
author: Ablage-System
triggers:
  - refactor
  - security audit
  - migration
  - optimize all
  - comprehensive
  - multi-file
  - across files
  - entire codebase
  - umfassend
  - vollstaendig
  - alle dateien
---

# Auto-Swarm Skill

Automatisches Spawnen von Claude Flow V3 Swarms wenn die Task-Komplexitaet es erfordert.

## Wann wird ein Swarm gespawnt?

### Automatisch bei Keywords:
- **Multi-File Operations**: "refactor", "across all files", "entire", "migration"
- **Security**: "security audit", "vulnerability scan", "penetration test"
- **Performance**: "optimize all", "performance audit", "bottleneck analysis"
- **Research**: "research", "analyze patterns", "compare approaches"
- **Testing**: "comprehensive tests", "e2e suite", "test coverage"

### Automatisch bei Datei-Anzahl:
- **>5 Dateien betroffen**: Swarm empfohlen
- **>10 Dateien betroffen**: Swarm stark empfohlen

## Verfuegbare Strategien

| Strategie | Beschreibung | Agents |
|-----------|--------------|--------|
| `auto` | Automatische Auswahl | 3-8 |
| `development` | Code-Entwicklung mit Review | 5-8 |
| `security` | Security Audit & Fixes | 4-6 |
| `refactoring` | Code-Refactoring | 4-6 |
| `testing` | Test-Erstellung & Ausfuehrung | 3-5 |
| `research` | Recherche & Analyse | 3-5 |
| `optimization` | Performance-Optimierung | 4-6 |

## Nutzung durch Claude

Claude kann automatisch Swarms spawnen:

```python
from .claude.orchestration.swarm_bridge import auto_swarm, spawn_swarm

# Automatische Entscheidung
result = auto_swarm(
    task="Refactor all API endpoints for consistent error handling",
    files=["app/api/v1/*.py"]
)

# Direktes Spawnen
result = spawn_swarm(
    task="Security audit the authentication system",
    strategy="security",
    max_agents=6
)
```

## Integration mit bestehender Orchestration

Der Swarm-Bridge integriert sich nahtlos mit:
- `mcp__orchestration__route_task` - Task-Routing
- `mcp__orchestration__decompose_task` - Task-Dekomposition
- Bestehendem Haiku/Sonnet/Opus Routing

## Beispiel-Workflow

1. User gibt komplexe Aufgabe
2. Claude analysiert Komplexitaet via `TaskComplexityAnalyzer`
3. Bei Score >= 3: Swarm wird empfohlen
4. Swarm spawnt automatisch mit passender Strategie
5. Ergebnisse werden in `.claude-flow/swarm-state.json` gespeichert

## Monitoring

Aktive Swarms koennen ueberwacht werden:
```bash
npx @claude-flow/cli@latest swarm status
npx @claude-flow/cli@latest monitor --focus swarm
```

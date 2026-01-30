---
name: auto-swarm
description: Automatisches Spawnen von Multi-Agent Swarms fuer komplexe Tasks
usage: /auto-swarm <task-beschreibung>
---

# Auto-Swarm Command

Spawnt automatisch einen Claude Flow V3 Swarm wenn die Task-Komplexitaet es erfordert.

## Verwendung

```
/auto-swarm Refactor all API endpoints for consistent error handling
/auto-swarm Security audit the authentication system
/auto-swarm Optimize all database queries
```

## Automatische Erkennung

Der Swarm wird automatisch gespawnt bei:

### Keywords (Hohe Komplexitaet)
- **Multi-File**: refactor, migration, across, all files, entire, complete
- **Security**: security audit, vulnerability, penetration, cve
- **Performance**: optimize, performance, bottleneck, profiling
- **Research**: research, analyze, investigate, compare
- **Testing**: comprehensive test, e2e, integration test, test suite

### Datei-Anzahl
- **>5 Dateien**: Swarm empfohlen
- **>10 Dateien**: Swarm stark empfohlen

## Strategien

| Strategie | Agent-Anzahl | Beschreibung |
|-----------|--------------|--------------|
| `auto` | 3-8 | Automatische Auswahl |
| `development` | 5-8 | Code + Review + Tests |
| `security` | 4-6 | Security Audit |
| `refactoring` | 4-6 | Code-Refactoring |
| `testing` | 3-5 | Test-Suite erstellen |
| `research` | 3-5 | Recherche & Analyse |
| `optimization` | 4-6 | Performance-Tuning |

## Integration

Claude nutzt dies automatisch bei komplexen Tasks. Der Befehl:

1. Analysiert Task-Komplexitaet
2. Entscheidet ob Swarm noetig
3. Waehlt optimale Strategie
4. Spawnt Swarm mit passenden Agents
5. Speichert Ergebnis in `.claude-flow/swarm-state.json`

## Beispiel-Output

```json
{
  "action": "swarm_spawned",
  "analysis": {
    "needs_swarm": true,
    "complexity_score": 5,
    "confidence": 0.85,
    "recommended_strategy": "security",
    "reasoning": "Komplexe Keywords: security audit, vulnerability"
  },
  "swarm_result": {
    "success": true,
    "swarm_id": "swarm_20260130_091500",
    "strategy_used": "security",
    "agents_spawned": 5,
    "duration_ms": 45000
  }
}
```

## Manuelle Nutzung (wenn noetig)

```bash
# Via CLI
npx @claude-flow/cli@latest swarm "Security audit" --strategy security --max-agents 6

# Status pruefen
npx @claude-flow/cli@latest swarm status

# Monitor
npx @claude-flow/cli@latest monitor --focus swarm
```

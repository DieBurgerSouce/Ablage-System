# Manifest w6e-core-rest

Stream: w6e-core-rest
Branch: feature/offensive-2026-06-11
Datum: 2026-06-14

## Nicht-gemountetes Paket: `.claude/orchestration` + `.claude/mcp-server`

### Befund
Die 15 Tests in `tests/unit/orchestration/` sind im `ablage-backend`-Container
**nicht sammelbar** (Collection-Error, EXIT=2):

```
ModuleNotFoundError: No module named 'orchestration'
```

Ursache (systemische Wurzel f — nicht-gemountetes Paket): Das Paket
`.claude/orchestration/` (und `.claude/mcp-server/`) existiert auf dem **Host**
(`C:/Users/benfi/Ablage_System/.claude/orchestration/`), ist aber **nicht** in
den Container gemountet. Verifiziert:

- `docker exec ablage-backend ls /app/.claude` -> `No such file or directory`
- `find / -name task_classifier.py -path "*orchestration*"` -> kein Treffer
- `/proc/mounts | grep claude` -> leer

Nur `/app/tests` + `/app/pytest.ini` sind gemountet (siehe MEMORY.md
"Test-Infra"). `.claude/` ist nicht Teil des Backend-Images.

### Betroffene Dateien (alle 15)
Alle importieren auf Modul-Ebene (vor conftest-Fallback) aus `orchestration.*`
bzw. `orchestration_server` bzw. inserten `.claude/orchestration` in `sys.path`:

- test_validators.py            (`from orchestration.validators ...`)
- test_shared_file_protocol.py  (`from orchestration.shared_file_protocol ...`)
- test_decision_cache.py        (`from orchestration.decision_cache ...`)
- test_orchestrator.py          (`from orchestration.orchestrator ...`)
- test_quality_gates_team.py    (`from orchestration.quality_gates ...`)
- test_task_classifier.py       (`from orchestration.task_classifier ...`)
- test_quality_gate.py          (`from orchestration.quality_gate ...`)
- test_token_counter.py         (`sys.path.insert(... .claude/orchestration)`)
- test_mcp_server.py            (`from orchestration_server import ...`)
- test_orchestration_metrics.py (`from orchestration.metrics ...`)
- test_team_workflow.py         (`from orchestration.team_workflow ...`)
- test_learning_feedback.py     (`from orchestration.learning_feedback ...`)
- test_user_feedback.py         (`from orchestration.user_feedback ...`)
- test_decision_cache.py / test_orchestrator.py (zusaetzlich task_classifier)

`conftest.py` der Zone hat zwar einen try/except-Mock-Fallback, aber die
einzelnen Testmodule importieren **direkt** (ohne Fallback) -> Collection bricht
vor dem Fallback ab.

### Empfehlung (NICHT von diesem Stream gemacht — Tabu/Manifest)
Diese Tests sind als **Host-Tests** konzipiert (laufen mit Host-Python, wo
`.claude/orchestration` liegt — sie testen das Team-Workflow-/Orchestration-
System aus `.claude/`, nicht `app/`). Optionen fuer den Owner:

1. **Host-Lauf** (vermutlich intendiert): `pytest tests/unit/orchestration/`
   mit `PYTHONPATH` inkl. `.claude` und `.claude/mcp-server` auf dem Host
   ausfuehren (nicht im Backend-Container).
2. Alternativ `.claude/orchestration` + `.claude/mcp-server` read-only in den
   Container mounten (docker-compose-Aenderung — ausserhalb dieses Streams).

Kein Code-Fix in der Zone moeglich/sinnvoll, solange das Paket fehlt. Kein
Self-Mount (Ressourcen-Disziplin, kein docker compose/restart).

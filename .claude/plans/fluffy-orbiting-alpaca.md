> **Status (W1-048, 2026-06-11)**: NICHT umgesetzt (kein ralph-stop-patcher/Session-Fix im git-log; letzte ralph-loop-Aktivität 2026-02-20, nur Timestamp-Commits).
> Vor Umsetzung Relevanz prüfen — der Loop wird aktuell nicht genutzt; ggf. archivieren.

# Plan: Cross-Instance Ralph-Loop Isolation Fix

## Context

Der ralph-loop Stop-Hook (`stop-hook.sh:27-35`) hat Session-Isolation, greift aber NICHT:

- `setup-ralph-loop.sh:144`: `session_id: ${CLAUDE_CODE_SESSION_ID:-}` → leer
- Stop-Hook:33: leere session_id = Guard skip → ALLE Instanzen blockiert
- Plugin-Dateien nicht patchbar (Updates ueberschreiben)

**Ziel**: Loop muss normal funktionieren UND nur in der startenden Instanz feuern.

## Schritt 1: Env-Var Test

```bash
echo "SESSION_ID='$SESSION_ID' CLAUDE_CODE_SESSION_ID='$CLAUDE_CODE_SESSION_ID'"
env | grep -i "session\|claude" || true
```

Falls eine Var gesetzt ist → diese in Schritt 2 nutzen → fertig.

Falls KEINE gesetzt → **Schritt 1b**: Stop-Hook bekommt session_id via JSON-Input (`jq -r '.session_id'`). Wir schreiben einen minimalen Stop-Hook-Patcher in `settings.json` der beim allerersten Stop-Event die session_id aus dem Hook-Input in die State-Datei schreibt (Self-Heal). Ab Iteration 2 greift dann die Isolation.

## Schritt 2: Projekt-Setup-Script

**Datei**: `.claude/scripts/setup-ralph-loop.sh` (NEU - Kopie von Plugin)

**Quelle**: `~/.claude/plugins/cache/claude-plugins-official/ralph-loop/205b6e0b3036/scripts/setup-ralph-loop.sh`

Einzige Aenderung (Zeile 140-151, State-File-Block):

```bash
# FIX: Session-ID aus verfuegbaren Env-Vars
SESSION_ID="${CLAUDE_CODE_SESSION_ID:-${SESSION_ID:-}}"

cat > .claude/ralph-loop.local.md <<EOF
---
active: true
iteration: 1
session_id: $SESSION_ID
max_iterations: $MAX_ITERATIONS
completion_promise: $COMPLETION_PROMISE_YAML
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---

$PROMPT
EOF
```

## Schritt 3: Projekt-Command umleiten

**Datei**: `.claude/commands/ralph-loop.md` (EDIT)

```markdown
---
description: "Start Ralph Loop in current session"
argument-hint: "PROMPT [--max-iterations N] [--completion-promise TEXT]"
allowed-tools: ["Bash(.claude/scripts/setup-ralph-loop.sh:*)"]
---

Execute the setup script to initialize the Ralph loop:

```!
".claude/scripts/setup-ralph-loop.sh" $ARGUMENTS
```

[Instruktionstext vom Plugin-Original uebernehmen]
```

## Schritt 4 (nur falls Schritt 1 zeigt: KEINE Env-Var verfuegbar)

**Self-Heal Stop-Hook** in `.claude/settings.json`

Neuen Stop-Hook VOR dem bestehenden einfuegen. Dieser liest den Hook-JSON-Input, patcht die session_id ins State-File falls leer, und gibt den Input via stdout weiter (damit der Plugin-Hook ihn trotzdem bekommt):

**Datei**: `.claude/scripts/ralph-stop-patcher.sh` (NEU)

```bash
#!/bin/bash
# Self-heal: Schreibt session_id ins State-File beim ersten Stop-Event
STATE=".claude/ralph-loop.local.md"
[ -f "$STATE" ] || exit 0

SID=$(sed -n 's/^session_id: *//p' "$STATE")
if [ -z "$SID" ]; then
  INPUT=$(cat)
  MY_SID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
  [ -n "$MY_SID" ] && sed -i "s/^session_id: */session_id: $MY_SID/" "$STATE"
  echo "$INPUT"  # Weiterreichen an naechsten Hook
else
  cat  # Durchreichen
fi
```

Stop-Hook in settings.json:
```json
{
  "type": "command",
  "command": "bash .claude/scripts/ralph-stop-patcher.sh",
  "timeout": 3000
}
```

**Hinweis**: Dieser Patcher muss VOR dem Plugin-Stop-Hook laufen. Er konsumiert stdin und gibt es via echo/cat wieder aus. Der Plugin-Hook bekommt den Output als seinen stdin (Pipeline-Verhalten von Claude Code Stop-Hooks muss verifiziert werden).

## Dateien

| Datei | Aktion | Bedingung |
|-------|--------|-----------|
| `.claude/scripts/setup-ralph-loop.sh` | **NEU** | Immer |
| `.claude/commands/ralph-loop.md` | **EDIT** | Immer |
| `.claude/scripts/ralph-stop-patcher.sh` | **NEU** | Nur falls keine Env-Var |
| `.claude/settings.json` | **EDIT** (Stop-Hook) | Nur falls keine Env-Var |

## Verifikation

1. `/ralph-loop "Test task" --max-iterations 3` in Instanz A
2. `grep session_id .claude/ralph-loop.local.md` → nicht leer
3. Instanz B: sollte NICHT vom Loop blockiert werden
4. Instanz A: Loop laeuft normal (3 Iterationen)
5. Aufraemen: `rm .claude/ralph-loop.local.md`

# Session-Dokumentation & Commit

Dokumentiert alle uncommitted Aenderungen, aktualisiert Memory-Dateien und CHANGELOG, erstellt Conventional Commits.

**Parameter:**
- Ohne Argumente: Normaler Ablauf (analysieren + committen)
- `dry-run` / `--dry-run` / `trocken`: Nur analysieren und Report zeigen, KEINE Commits erstellen
- `--scope <bucket>` / `scope:<bucket>`: Nur den angegebenen Bucket committen
- `--since <commit>` / `since:<commit>`: Nur Aenderungen seit dem angegebenen Commit

Gueltige Scopes: ocr, api, security, frontend, db, services, workers, infra, orchestration, tests, config

Beispiele:
- `/docu` → Alles
- `/docu dry-run` → Nur analysieren
- `/docu scope:ocr` → Nur OCR-Dateien committen
- `/docu scope:frontend` → Nur Frontend committen
- `/docu since:abc1234` → Nur Aenderungen seit Commit abc1234
- `/docu since:HEAD~3` → Nur die letzten 3 Commits + uncommitted

**Was passiert:**
1. Analysiert `git status` und `git diff`
2. Gruppiert Aenderungen in logische Commit-Buckets (ocr, api, services, etc.)
3. Aktualisiert `.claude/memory/RECENT_CHANGES.md`, `CHANGELOG.md` und ggf. weitere Memory-Files
4. Pruned RECENT_CHANGES.md wenn >50 Zeilen (archiviert nach `.claude/Docs/Archive/`)
5. Erstellt 2-6 selektive Conventional Commits
6. Zeigt Zusammenfassung

**Instruktionen:**

Wenn $ARGUMENTS "dry" oder "trocken" enthaelt, uebergib dem Agent den DRY-RUN Modus:

```
Task(
  prompt: "Du bist der Session-Documenter Agent. Fuehre deinen kompletten Workflow aus. Arbeite selbststaendig ohne Rueckfragen. Das Working Directory ist C:\\Users\\benfi\\Ablage_System. MODUS: DRY-RUN. Fuehre Phase 0-4 aus, ueberspringe Phase 5-6. Zeige in Phase 7 was committed WUERDE.",
  subagent_type: "session-documenter",
  description: "Session documentation dry-run",
  mode: "bypassPermissions"
)
```

Wenn $ARGUMENTS "scope:" oder "--scope" enthaelt, extrahiere den Bucket-Namen und uebergib dem Agent:

```
Task(
  prompt: "Du bist der Session-Documenter Agent. Fuehre deinen kompletten Workflow aus. Arbeite selbststaendig ohne Rueckfragen. Das Working Directory ist C:\\Users\\benfi\\Ablage_System. MODUS: SCOPE-FILTER. Fuehre alle Phasen aus, aber committe in Phase 5 NUR den Bucket: <scope>. Alle anderen Buckets in der Zusammenfassung als 'uebersprungen (nicht im Scope)' auffuehren.",
  subagent_type: "session-documenter",
  description: "Session documentation scoped commit",
  mode: "bypassPermissions"
)
```

Wenn $ARGUMENTS "since:" oder "--since" enthaelt, extrahiere den Commit-Ref und uebergib dem Agent:

```
Task(
  prompt: "Du bist der Session-Documenter Agent. Fuehre deinen kompletten Workflow aus. Arbeite selbststaendig ohne Rueckfragen. Das Working Directory ist C:\\Users\\benfi\\Ablage_System. MODUS: SINCE-FILTER. Nutze in Phase 1 statt 'git diff HEAD' den Befehl 'git diff <commit>' um nur Aenderungen seit <commit> zu sehen. Committed-but-not-pushed Aenderungen werden als eigene Eintraege in der Zusammenfassung gelistet.",
  subagent_type: "session-documenter",
  description: "Session documentation since commit",
  mode: "bypassPermissions"
)
```

Ansonsten normaler Ablauf:

```
Task(
  prompt: "Du bist der Session-Documenter Agent. Fuehre deinen kompletten Workflow aus. Arbeite selbststaendig ohne Rueckfragen. Das Working Directory ist C:\\Users\\benfi\\Ablage_System",
  subagent_type: "session-documenter",
  description: "Session documentation and commits",
  mode: "bypassPermissions"
)
```

**Hinweis:** Der Agent arbeitet selbststaendig und meldet sich mit einer Zusammenfassung zurueck. Kein Eingriff noetig.

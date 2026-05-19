/goal Squash-Merge sprint-0-pilot-hardening -> master (Pilot-Ship v0.1.0)

Ziel: PR #8 (https://github.com/DieBurgerSouce/Ablage-System/pull/8) als sauberer Squash-Merge nach master ueberfuehren, Pilot-Tag setzen, Branch sauber abraeumen, Memory/CHANGELOG nachziehen. Branch enthaelt 561 Commits aus drei Monaten Sprint-0-Pilot-Hardening + Phase A + Phase B + Multi-Agent-Review Follow-Through (A-D, F1-F4) + Sprint-1 Sec-Reste (S1.1-S1.5). KEINE Code-Aenderungen mehr - reines Ship-Operations.

Quelle: `.claude/reviews/2026-05-19/MASTER_REVIEW_2026-05-19.md`, `C:\Users\benfi\.claude\plans\guck-dir-bitte-nochmal-recursive-lollipop.md`, `SPRINT_0_OPEN.md`, `.claude/memory/RECENT_CHANGES.md`.

---

**S0 (5min) — Pre-Conditions sicherstellen**
Vor jedem Schritt verifizieren:
1. `git fetch origin && git status` — Working tree clean ausser den 5 Runtime-Artefakten in `.claude-flow/metrics/*.json` (die bleiben lokal, nicht committen). Falls weitere uncommitted: STOPP, klaeren mit User.
2. `git branch --show-current` — aktuell `sprint-0-pilot-hardening`. Falls nicht: `git switch sprint-0-pilot-hardening`.
3. `git log origin/sprint-0-pilot-hardening..HEAD --oneline` — leer (local == remote). Falls nicht: `git push origin sprint-0-pilot-hardening` zuerst.
4. `gh pr view 8 --json mergeable,statusCheckRollup,reviewDecision` — pruefen ob CI gruen und PR mergebar. Falls `mergeable != MERGEABLE`: in der CLI-Ausgabe Ursache identifizieren (Merge-Konflikte, fehlende Checks). KEIN merge bei rotem CI.
5. `gh pr checks 8` — alle Checks listen. Falls einzelne rot sind: User fragen ob Override gewollt ist (Pilot-Ship-Druck vs. CI-Disziplin). Default: STOPP wenn Checks rot.

**S1 (15min) — Saubere Squash-Commit-Message vorbereiten**
GitHub-Default-Squash interpoliert Title + alle 561 Commit-Messages = unleserlich. Stattdessen kuratierte Message in `docs/pr/pr-8-squash-message.md` schreiben mit folgendem Geruest:

```
feat(pilot): Sprint-0 Pilot-Hardening + Sprint-1 Sec-Reste -> Pilot-Ship v0.1.0 (PR #8)

Konsolidiert 561 Commits aus drei Monaten sprint-0-pilot-hardening in vier
groesseren Arbeitspaketen. Severity gegen master: 5 CRITICAL + 11 HIGH-Security
gefixt. Branch ab Merge-Base 2cfdc17d.

== Sprint-0 Pilot-Hardening (G01-G10, ~3.5h real vs 14h geplant) ==
- 4e01c076 feat: Notification + Security + Watchdog (G01,G02,G04,G05,G07,G08,G10)
- 20c9bb1b fix: Sentry-Aktivierung + arm64-amd64-Digest + Janus-Skip-Option
- 6de2d89e fix: Worker-Import-Bugs + Loki-Alert-Rule + Prometheus-Cleanup
- 7e012828 fix: Alertmanager-Tuning + Backup-Metric-Fix + Watchdog-Cooldown
- 438f2486 fix: Slack-Spam-Sweep (Qdrant-Auth, Worker-Healthcheck, Rule-Hygiene)
- 90c26e03 docs(changelog): Phase A Pilot-Ship Blocker dokumentieren

== Phase A — 6 Pilot-Ship Blocker (MASTER_REVIEW_2026-05-19) ==
- 5db272f9 K1 (CRITICAL) 15 Alembic dangling Heads zu 1 Head konsolidiert
- 12f24731 K2 (CRITICAL) deploy.yml Test-Gate auf CI-Erfolg
- K3 False-Positive (build_content_disposition ist via __init__.py re-exportiert)
- d605d76e K4 (CRITICAL) dpia.py Multi-Tenant Bypass geschlossen
- fbef51c5 K5 (CRITICAL) notification_rules /test DoS-Schutz
- 8c78a68e K6 (CRITICAL) event_sourcing aggregate_type Whitelist

== Phase B — 7 Discipline-Items ==
- ee702408 B1 Doc-Formatter-Revert + Prettier-Guard
- bace67f4 B2 Frontend Logger-Sweep (69x console.* -> logger.*)
- 8b4b37bf B3 Pydantic-v2 Codemod (84 Patterns)
- 74ed7b2d B4 Rate-Limit auf 12 ungeschuetzte Router
- cbfdb217 B5 Top-5 Tests (74 neu + 3 Integration-Stubs)
- 33c84712 B6 GPU-Thermal-Alerts reaktiviert
- ee155e21 B7 Mutable Image-Tags auf SHA pinnen
- 409da931 chore: Phase B Housekeeping (gitignore + audit-baseline + vault-script)

== Multi-Agent-Review Follow-Through (Tasks A-D, F1-F4) ==
- 74210d8e Task A: .env.example um 37 Vars (Drift schliessen)
- 37baeb94 Task B: Invoice-Model company_id Drift-Fix
- e1e99825 Task C/F3: Invoice-API 19 Endpoints owner_id -> company_id
- 1b0c76d3 Task D: Alertmanager SMTP-Auth via file-mount
- 81ff78c1 F1: business_contact_id Phantom aus Invoice-Model
- 7badff26 F2: BI-Service Invoice.entity_id Runtime-Bombe JOIN
- 8ad8045b docs(session): Multi-Agent Review Follow-Through dokumentiert

== Sprint-1 Sec-Reste (HIGH-Sec, 2026-05-20) ==
- 59a5702f S1.2 (HIGH) retention_admin.py safe_error_detail Args swap
- cf062e80 S1.3 (HIGH, CWE-89) graphql_api.py Filter-Allow-List pro Entity
- dd693f14 S1.4 (HIGH) nlq.py generated_sql Admin-Gate
- d56cd145 S1.5 F4 InvoiceTracking.entity_id Drift-Cleanup
- e8f6badb S1.1 (HIGH) trash.py company_id-Filter + Bulk-Delete + Audit
- 87e8b4f2 docs(session): Sprint-1 Sec-Reste dokumentiert

== Bewusst NICHT in diesem PR (Pilot-Backlog) ==
- G10 Sentry-DSN (User-Action, .env)
- P0b 9 aktive Critical Alerts triage (vor Pilot-Start)
- Phase C Type-Safety (305 `as any`, 86 `Dict[str, Any]`, File-Splits, i18n-Decision)
- Phase D Tests (test_mfa, test_encryption, test_gdpr_deletion_e2e, test_cross_tenant_attack_matrix, Edge-Cases-Klassen + 4 Sprint-1-Sec-Tests)
- Phase E RAG-Spec (PDF-Generator, Customer-Card Beat, Performance-Benchmarks)
- BACKLOG: collaboration.py safe_error_detail Misuse (12 Stellen, kein PII-Leak)
- BACKLOG: Pre-Commit-Hook gegen safe_error_detail Args-Verdrehung

Plan: `C:\Users\benfi\.claude\plans\guck-dir-bitte-nochmal-recursive-lollipop.md`
Review: `.claude/reviews/2026-05-19/MASTER_REVIEW_2026-05-19.md`

Co-Authored-By: claude-flow <ruv@ruv.net>
```

WICHTIG bei der Vorbereitung:
- Datei `docs/pr/pr-8-squash-message.md` anlegen, MIT obigem Inhalt. Falls Verzeichnis nicht existiert: `mkdir -p docs/pr`.
- KEIN Commit dieser Datei vor dem Merge - sie ist nur Eingabe fuer `gh pr merge --body`. Wenn sie versehentlich committed wird: in S2 wieder loeschen.
- Alternativ: Text als Heredoc direkt in den `gh pr merge`-Call piepen (siehe S2).

**S2 (5min) — Squash-Merge ausfuehren**
```bash
gh pr merge 8 --squash --delete-branch \
  --subject "feat(pilot): Sprint-0 Pilot-Hardening + Sprint-1 Sec-Reste -> Pilot-Ship v0.1.0 (PR #8)" \
  --body-file docs/pr/pr-8-squash-message.md
```

Falls `--body-file` Probleme macht (z.B. wegen Windows-Pfad): stattdessen `--body "$(cat docs/pr/pr-8-squash-message.md)"` mit Heredoc.

`--delete-branch` raeumt remote-Branch automatisch ab. Lokalen Branch separat in S4.

WICHTIG: KEIN `--admin` nutzen, kein Override-Flag. Wenn der Merge fehlschlaegt, hat das einen Grund (CI rot, Branch-Protection, etc.) - User fragen, nicht erzwingen.

**S3 (3min) — master pullen + Tag setzen**
```bash
git switch master
git pull origin master --ff-only
```

`--ff-only` schuetzt vor versehentlichem Merge-Commit falls master inzwischen weitergelaufen ist. Wenn der Pull fehlschlaegt: STOPP, User informieren.

Tag setzen:
```bash
git tag -a pilot-v0.1.0 -m "Pilot-Ship v0.1.0

Sprint-0 Pilot-Hardening + Phase A + Phase B + Multi-Agent-Review
Follow-Through (A-D, F1-F4) + Sprint-1 Sec-Reste (S1.1-S1.5).

Erste produktive Pilot-Version. Branch sprint-0-pilot-hardening
gemerged via Squash. Source: PR #8.

Backlog vor produktiver Nutzung:
- Sentry-DSN setzen (User, ~5min)
- 9 aktive Critical Prometheus-Alerts triagieren
- Tests fuer 4 Sprint-1-Sec-Fixes (Phase D)
"
git push origin pilot-v0.1.0
```

**S4 (2min) — Lokalen Branch abraeumen**
```bash
git branch -d sprint-0-pilot-hardening
```

Falls `-d` fehlschlaegt mit "not fully merged" (passiert nach Squash, weil der originale Commit-Hash nicht im master ist): mit `-D` forcen, ABER nur wenn der `gh pr merge` in S2 sauber durchlief. Verifikation vor `-D`:
- `gh pr view 8 --json state` zeigt `MERGED`
- `git log master --oneline | head -5` zeigt den neuen Squash-Commit

Dann `git branch -D sprint-0-pilot-hardening`.

`git remote prune origin` falls remote-Branch lokal noch als tracking-ref existiert.

**S5 (10min) — Memory + CHANGELOG nachziehen**
Auf `master` (jetzt mit Squash-Commit als Tip):
1. `.claude/memory/RECENT_CHANGES.md` — neuen Block ganz oben:
   ```
   ## 2026-05-20 (Pilot-Ship v0.1.0)
   PR #8 squash-gemerged: sprint-0-pilot-hardening -> master. Tag pilot-v0.1.0.
   Squash-Commit: <SHA aus `git log master -1 --format=%H`>.
   Pakete: Sprint-0 G01-G10, Phase A K1-K6, Phase B B1-B7, Multi-Agent-Review
   Follow-Through (A-D, F1-F4), Sprint-1 Sec-Reste (S1.1-S1.5).
   ```
2. `.claude/memory/PROJECT_STATUS.md` — Recent-Deployments-Tabelle: neuer Eintrag oben:
   `| 2026-05-20 | Release | Pilot-Ship v0.1.0 (Squash PR #8) - <SHA> |`
3. `CHANGELOG.md` — `## [Unreleased]` Header zu `## [0.1.0] - 2026-05-20 (Pilot-Ship)` aendern, neuen leeren `## [Unreleased]` darueber. Alle Unreleased-Eintraege bleiben unter v0.1.0.

Diese 3 Aenderungen in einem Commit:
```bash
git add .claude/memory/RECENT_CHANGES.md .claude/memory/PROJECT_STATUS.md CHANGELOG.md
git commit -m "docs(release): Pilot-Ship v0.1.0 Squash-Merge dokumentieren"
git push origin master
```

**S6 (5min) — Verifikation (Definition of Done)**
1. `gh pr view 8 --json state,mergedAt` → state=`MERGED`, mergedAt gesetzt
2. `git log master --oneline | head -3` zeigt den Squash-Commit + den S5-Doc-Commit
3. `git tag --list 'pilot-*'` enthaelt `pilot-v0.1.0`
4. `gh release list | head -3` zeigt das Tag (auf GitHub sichtbar)
5. `git branch --list 'sprint-0-pilot-hardening'` leer (lokal weg)
6. `gh api repos/DieBurgerSouce/Ablage-System/branches/sprint-0-pilot-hardening 2>&1 | grep -i "Not Found"` — remote weg
7. `git log master..pilot-v0.1.0 --oneline` leer (Tag zeigt auf master HEAD)
8. Smoke-Test auf master: `python -c "from app.api.v1 import trash, retention_admin, graphql_api, nlq; from app.db.models_entity_business import InvoiceTracking; assert 'entity_id' in [c.name for c in InvoiceTracking.__table__.columns]; print('OK')"`

**Rollback (falls etwas schiefgeht)**
- Vor S2: `gh pr ready 8 --undo` (PR zurueck auf Draft) und User informieren.
- Nach S2, vor S3: Squash-Commit revert: `git revert -m 1 <squash-sha>` auf master, push. Branch wieder herstellen: `git push origin <local-backup>:sprint-0-pilot-hardening` (falls vorher Backup gemacht).
- Nach S3: Tag loeschen: `git tag -d pilot-v0.1.0 && git push origin :refs/tags/pilot-v0.1.0`.
- Nach S4: Branch wieder herstellen aus Reflog: `git reflog show sprint-0-pilot-hardening` -> `git branch sprint-0-pilot-hardening <reflog-sha>`.

**Out of Scope** (nicht in diesem /goal)
- Pre-Block P0b (9 Critical Alerts triage) — laeuft separat, blockiert nicht den Merge selbst (war als "vor Pilot-Start" geplant, nicht "vor Merge")
- Sentry-DSN setzen — User-Action
- Phase C/D/E — naechste Sprints
- Branch-Protection-Regeln auf master einfuehren — separater Sprint (jetzt nur Squash-Discipline manuell)

**Anti-Pattern (NICHT machen)**
- `gh pr merge --merge` (ohne squash): erzeugt einen Merge-Commit + behaelt alle 561 Commits in der master-History.
- `gh pr merge --rebase`: rewriteten der 561 Commits auf master, ebenfalls unleserlich.
- `git push --force`: NIE auf master.
- `--admin` Flag bei `gh pr merge`: umgeht Branch-Protection und versteckt mogliche Fehlerquellen.
- Tag setzen VOR dem Squash-Merge: Tag wuerde auf einen toten Commit zeigen.
- Lokalen Branch loeschen VOR der gh-Verifikation dass der Merge wirklich durchlief.

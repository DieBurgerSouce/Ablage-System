# Merge-Konflikt-Analyse: sprint-0-pilot-hardening vs master

**Datum**: 2026-05-20
**Trigger**: GOAL_SQUASH_MERGE S0 Pre-Check zeigt `gh pr view 8 --json mergeable` = `CONFLICTING`
**Safety-Tag**: `pre-merge-master-backup-2026-05-20` (auf 8d9b89fe)

## Branch-Topologie

| Branch | HEAD | Datum | Commits seit Merge-Base |
|--------|------|-------|-------------------------|
| `master` | `9a8140ad` | 2026-01-04 | 3 (Tier-1 Transformation) |
| `sprint-0-pilot-hardening` | `8d9b89fe` | 2026-05-20 | 562 (3 Monate Pilot-Arbeit) |
| Merge-Base | `2cfdc17d` | 2025-12-? | - |
| `develop` | `824d7bc3` | uralt, vor Merge-Base | - |
| `staging` | `0e130f0e` | mitten in Tier-1 (master vorletzter) | - |

**Kern-Problem**: Master ist seit 4 Monaten nicht mehr im Pilot-Branch integriert worden. Master's 3 Commits sind eine "Global Tier-1 Transformation" (Identity-Rebrand + Repo-Hygiene), die parallel zur Pilot-Arbeit lief.

## Was master in den 3 Commits geändert hat

1. **Identity-Rebrand** (`f6d8c843`):
   - `package.json` + `pyproject.toml`: URL `ablage-system/ablage-system-ocr` → `DieBurgerSouce/Ablage-System`, Author/Maintainer-Strings, Homepage.
   - `.github/CODEOWNERS`: `@your-org/*` → `@DieBurgerSouce/*` (alle Team-Strings)
   - `.vscode/`: komplettes IDE-Setup neu (extensions, launch, settings, tasks, snippets)
   - `VERSION`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CONVENTIONS.md`: neue Root-Files
   - `.releaserc.json`, `.yamllint.yml`, `.markdownlint.json`: aus `scripts/temp/` ins Root verschoben
   - `app/uploads/*.png` als Binary-Files gecheckt
2. **Strict Root Policy** in `.gitignore`:
   ```
   /*
   !/.gitignore
   !/.dockerignore
   ... (Whitelist von erlaubten Root-Files)
   ```
   Alle nicht-whitelisteten Files im Root werden gitignored.
3. **Doku-Reorganisation** (~80 .md-Files):
   - Master sortiert in `docs/analysis/` (Sammelordner)
   - Branch sortiert in `docs/auth/`, `docs/celery/`, `docs/deployment/`, `docs/guides/`, `docs/implementation/` (semantische Gruppen)

## Konflikt-Inventur (`git merge master --no-commit`)

**Total 109 Konflikte** klassifiziert nach git-Status-Code:

| Klasse | Anzahl | Beschreibung |
|--------|--------|--------------|
| `UU` Inhaltskonflikt | 2 | `.github/CODEOWNERS`, `.gitignore` |
| `UD` Modified-by-us / Deleted-by-them | 2 | `CONVENTIONS.md`, `DEPLOYMENT.md` |
| `UA` Modified-by-us / Added-by-them | ~50 | Doku-Files: master hat sie nach `docs/analysis/` einsortiert (Add), branch hat sie in andere Subordner (Modify durch Rename) |
| `AU` Added-by-us / Modified-by-them | ~50 | Spiegelbild: branch hat sie nach `docs/auth/` etc. einsortiert, master kennt diese Pfade nicht |
| `AA` (rename/rename) | ~22 | Beide Seiten haben gleiche Files umbenannt, aber zu unterschiedlichen Pfaden (z.B. `test_easyocr.py` → `tests/_archived/manual/` vs `tests/e2e/scripts/`) |
| `rename/delete` | 1 | `ocr_result.json` master nach `scripts/temp/`, branch hat es gelöscht |

**Auto-merged ohne Konflikt** (überraschend): `package.json`, `pyproject.toml`. Git konnte die identity-Strings als kompatibel mergen.

## Optionen zur Konflikt-Auflösung

### Option A: Branch gegen master mergen, alle Konflikte resolven
**Aufwand**: 2-4h, gross
**Vorgehen**:
1. `git merge master --no-commit`
2. Für jeden der 109 Konflikte einzeln entscheiden
3. Defaults: Branch-Pfade gewinnen für Dokus, master gewinnt für Identity-Strings (CODEOWNERS, package.json, pyproject.toml — diese sind ohnehin auto-merged), `.gitignore` Strict-Root-Policy in eigenen Branch verschieben
4. Commit als Merge-Commit, push
5. Dann GOAL_SQUASH_MERGE wieder versuchen

**Risiko**: Hoch - 107 mechanische Entscheidungen, jede mit semantischer Implikation. Branch-Pfade vs Master-Pfade-Entscheidung muss konsistent sein.

### Option B: Identity-Cherry-Pick (empfohlen)
**Aufwand**: 1-2h, mittel
**Vorgehen**:
1. Auf einem temporären Branch `pilot-with-identity` von `sprint-0-pilot-hardening` ausgehen
2. `git cherry-pick f6d8c843 0e130f0e` (die 2 Tier-1-Commits, der dritte `9a8140ad` ist nur ein Merge)
3. Konflikte beschränken sich auf die ~5 echten Inhaltskonflikte (CODEOWNERS, package.json, pyproject.toml, .gitignore, =2.0.0)
4. Doku-Reorganisation von master VERWERFEN (Branch's Struktur ist semantisch besser)
5. Cherry-pick committen, Branch als neuen sprint-0 force-pushen
6. PR #8 hat dann nur noch echte Identity-Diffs ggn master → mergeable

**Vorteil**: Sauberer + reversibler, behält Branch's Doku-Struktur, übernimmt Identity-Rebrand
**Risiko**: Mittel - cherry-pick kann Konflikte werfen, aber nur 3 Commits, nicht 562

### Option C: Master rebasen
**Aufwand**: 0.5h, gering, ABER drastisch
**Vorgehen**:
1. `git checkout master`
2. `git reset --hard sprint-0-pilot-hardening` (master = branch)
3. `git push --force-with-lease origin master` (Identity-Rebrand verloren!)

**Vorteil**: Schnell, einfach
**Nachteil**: Tier-1-Transformation **komplett verloren**. Repo-Identity bleibt auf altem Stand `ablage-system/ablage-system-ocr` (was das remote heisst). Branch-Pflege muss in separatem Sprint nachgeholt werden.

### Option D: PR #8 schliessen, neuer PR gegen develop
**Aufwand**: 0.1h, sehr klein
**Vorgehen**:
1. `develop` ist auf `824d7bc3` (vor merge-base) - nicht hilfreich, wäre noch mehr Konflikte
2. Neuer Branch `release/pilot-v0.1.0` von master als Target erstellen, parallel zu master
3. Branch dorthin mergen statt auf master
4. Tier-1-Identity bleibt auf master, Pilot ist ein paralleler Stream

**Vorteil**: Vermeidet Konflikt komplett
**Nachteil**: Pilot kommt nie auf master, "master" als ungenutzter Brand-Branch

### Option E: Squash zu einem Commit auf master-Basis
**Aufwand**: 1-2h, hoch
**Vorgehen**:
1. `git checkout -b pilot-flat master`
2. `git checkout sprint-0-pilot-hardening -- .` (alle Branch-Files in einen master-basierten WC kopieren)
3. `git restore --source=master --staged --worktree .github/CODEOWNERS .gitignore package.json pyproject.toml` (Master-Identity erhalten)
4. `git rm "=2.0.0"`
5. Optional: Doku-Files aus `docs/analysis/` ins Branch-Schema zurück verschieben
6. Commit als Squash, force-push als sprint-0-pilot-hardening
7. PR #8 update zeigt einen Commit der mergeable ist

**Vorteil**: Volle Kontrolle, sauberer Squash, kein 109-Konflikt-Marathon
**Nachteil**: Manuelle Datei-Operationen, hoher Aufwand, erfordert Disziplin

## Empfehlung

**Option B (Identity-Cherry-Pick)**, weil:
- Erhält Tier-1-Identity (geringe aber wichtige Änderung)
- Erhält Pilot-Doku-Struktur (semantisch besser als master's Sammelordner)
- Nur 3 Commits zu integrieren statt 109 Konflikte
- Reversibel via Safety-Tag

**Falls Option B Konflikte wirft, die sich auch in den 5 üblichen Verdächtigen aussern**: Option E als Fallback.

## Out of Scope (separate Sprints)

- Strict Root Policy aus master in Pilot integrieren (eigener Sprint nach Pilot-Ship)
- Doku-Reorganisation zwischen `docs/analysis/` und semantischen Subordnern vereinheitlichen
- `.vscode/`-Setup aus master in Pilot übernehmen
- Binary-Files (`app/uploads/*.png`) - sollten ohnehin nicht in Git (siehe Strict Root Policy)

## Next-Step-Empfehlung

User entscheidet zwischen Option A-E. Bei Option B kann ich direkt loslegen ohne weitere Approvals.

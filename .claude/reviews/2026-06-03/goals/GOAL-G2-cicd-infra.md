<!--
/goal-Prompt — Strom G2: CI/CD + Infrastruktur + operative Security
WELLE 1 — laeuft parallel mit G1, G3, G4 (komplett unabhaengig, kein app/-Code). Worktree/Branch: feature/g2-cicd
Den Text ab "===" als /goal in eine Claude-Code-Session einfügen.
-->

=== GOAL G2 ===

Setze Remediation-Strom **G2 (CI/CD + Infrastruktur + operative Security)** fuer das Projekt "Ablage-System" um. Repo-Root: `C:\Users\benfi\Ablage_System`, Default-Branch ist `master` (es gibt KEINEN `main`-Branch remote).

## Scope-Grenze (HART)
Du darfst AUSSCHLIESSLICH diese Dateibaeume anfassen: `.github/**`, `docker/**`, `docker-compose*.yml`, `.secrets.baseline`, `.pre-commit-config.yaml`, `requirements*.txt`, `.releaserc.json`. KEIN `app/`-Code, KEIN `.claude/**`, KEIN `frontend/src`. Doku-Korrekturen in `.claude/CLAUDE.md` (Port 5433->5434) gehoeren NICHT dir — nur als Hinweis im Abschlussbericht vermerken.

## Verifizierte Ausgangslage (vorab geprueft)
- `docker-compose.yml` nutzt als Single Source of Truth: Root-`Dockerfile` (Backend + Worker), `frontend/Dockerfile` (Frontend, Build-Context `./frontend`). `docker/Dockerfile.worker` existiert.
- ABER `ci.yml`, `docker.yml`, `docker-build.yml`, `dependencies.yml` bauen aus NICHT existierenden `docker/Dockerfile.backend` und `docker/Dockerfile.frontend` -> Build-Jobs sind Fassaden.
- Alle Workflows triggern auf `main`/`[main,develop]` statt `master` -> Gates laufen real nie.
- Root-`Dockerfile` und `infrastructure/docker/Dockerfile.backend` haben BEIDE keine `development`-Stage; `docker-compose.dev.yml` referenziert aber `target: development` -> bricht.
- `.secrets.baseline` ist `{}` (ungueltig). `detect-secrets` ist nicht installiert.
- `dependencies.yml` ruft `pip-compile requirements.in` auf — `requirements.in` existiert nicht. `safety check ... || true` maskiert alle Funde.
- `.github/dependabot.yml` existiert, docker-Ecosystem zeigt nur auf `/docker` (verfehlt Root- und Frontend-Dockerfile).
- `infrastructure/kubernetes/` UND `infrastructure/helm/` existieren beide. k8s-deploy.yml triggert aber auf `push.branches:[main]`.
- canary-deploy.yml ruft `docker-compose exec nginx` — es gibt keinen top-level `nginx`-Service (nur in `infrastructure/nginx/docker-compose.nginx.yml`); zusaetzlich verschachtelte Heredocs (NGINX_EOF eingerueckt -> kaputt).
- deploy.yml prueft `migrations/versions` — real ist `alembic/versions`.
- VERSION-Datei = `0.1.0-dev`. `.releaserc.json` (semantic-release, branch `main`) widerspricht hand-gerolltem `release.yml`.

## Aufgaben (in dieser Reihenfolge)
1. **Dockerfile-Quellen konsolidieren (Option A: Workflows umbiegen, KEINE neuen docker/-Dateien):** In `ci.yml` (Job `build`), `docker.yml` (matrix), `docker-build.yml`, `dependencies.yml` (docker-updates matrix) jedes `docker/Dockerfile.backend` -> `Dockerfile` (context `.`); jedes `docker/Dockerfile.frontend` -> `frontend/Dockerfile` mit context `./frontend`; `docker/Dockerfile.worker` unveraendert lassen (existiert). Ziel: CI, docker.yml, docker-build.yml und Compose bauen aus exakt denselben 3 realen Dateien.
2. **Branch-Trigger auf master:** In ALLEN `.github/workflows/*.yml` `branches: [main]`/`[main, develop]` -> `master` ergaenzen/ersetzen (`[master, develop]`); `refs/heads/main` -> `refs/heads/master`; in `release.yml` `git push origin main` -> `git push origin master`; `workflow_run.branches:[main]` (deploy.yml) -> `master`. Per Grep luckenlos pruefen. `is_default_branch`-Tags nicht anfassen.
3. **docker-compose.dev.yml:** backend/worker/flower build auf Root-`Dockerfile` bzw `docker/Dockerfile.worker` umstellen und `target: development` ENTFERNEN (Hot-Reload laeuft ueber volume-mount + `uvicorn --reload`, keine Build-Stage noetig).
4. **deploy.yml:** Pfad `migrations/versions` -> `alembic/versions` (Step 'Check for Breaking Changes').
5. **canary-deploy.yml:** Da kein nginx-Compose-Service existiert und der Workflow workflow_dispatch-only ist: DEAKTIVIEREN (Job-Guard `if: false` + Kopf-Kommentar 'Canary nicht konfiguriert: top-level nginx-Service fehlt, siehe infrastructure/nginx/'). Optional voll reparieren (nginx-Aufrufe auf `infrastructure/nginx/docker-compose.nginx.yml` + Heredocs entschachteln) nur wenn zuegig moeglich.
6. **k8s-deploy.yml:** `on.push.branches:[main]` -> `master`. Validate/Helm-Jobs bleiben (Verzeichnisse existieren). Wenn das Team kein k8s nutzt, optional push-Trigger entfernen (workflow_dispatch-only).
7. **.secrets.baseline neu erzeugen:** `pip install detect-secrets==1.4.0` (passend zu pre-commit-rev v1.4.0), dann `detect-secrets scan --all-files --exclude-files 'frontend/node_modules/.*' --exclude-files 'package-lock\.json' > .secrets.baseline`. Baseline manuell sichten — KEINE echten Keys/PII whitelisten (CRITICAL Rule 1/8); bei echten Funden Secret melden statt aufnehmen.
8. **dependencies.yml + ci.yml security:** `safety check ... || true` durch blockierendes `pip-audit -r requirements.txt` (ohne `|| true`) ersetzen, JSON-Report-Upload behalten. python-dependencies-Job (pip-compile requirements.in) entfernen (Updates uebernimmt Dependabot). docker-updates matrix auf `Dockerfile`, `docker/Dockerfile.worker`, `frontend/Dockerfile` korrigieren.
9. **dependabot.yml:** docker-Ecosystem-Eintraege fuer `directory: /` und `directory: /frontend` ergaenzen (zusaetzlich zu `/docker`). pip/npm/actions/terraform bleiben.
10. **Release vereinheitlichen:** EINEN Mechanismus waehlen. Empfehlung semantic-release: `.releaserc.json` `branches` `main`->`master`; `release.yml` zu duennem `npx semantic-release`-Wrapper umbauen (eigene bash-Versionslogik + deprecated `actions/create-release` entfernen). Falls manuelle Releases gewuenscht sind: nur Branch-Fix (main->master) in release.yml, Mechanismus-Wechsel weglassen — dann im Bericht begruenden.
11. **OPTIONAL CI-Guard** (nur wenn `import app.workers.celery_app` in CI ohne DB/Redis sauber gelingt, sonst weglassen + TODO): Neuer ci.yml-Job analog `alembic-heads-check`, der jeden `beat_schedule`-Tasknamen gegen `celery_app.tasks` und jedes `app/workers/tasks/*.py` gegen die `include=[...]`-Liste prueft, bei Abweichung `::error::` + exit 1. Nur ci.yml editieren, KEIN app/-Code. (Hinweis: G4 aendert die include[]/beat_schedule-Struktur — diesen Guard erst nach G4-Merge final scharf stellen oder tolerant schreiben.)

## Constraints
- Alle NEUEN user-facing Texte/Logs deutsch (UTF-8 Umlaute). Keine PII/Secrets/Keys in Logs oder Repo (Rule 1/8).
- Idempotente, reproduzierbare Workflows; SHA-gepinnte Actions beibehalten (Bestandsstil).
- Keine neuen Dateien ausser `.secrets.baseline`-Neugenerierung anlegen, wo bestehende editierbar sind.

## Definition of Done
- `grep -rn 'docker/Dockerfile.backend\|docker/Dockerfile.frontend' .github/ docker-compose*.yml` -> 0 Treffer.
- `grep -rn 'branches: \[main\|refs/heads/main\|origin main' .github/workflows/` -> 0 Treffer.
- `docker build -f Dockerfile -t t-be .` + `docker build -f frontend/Dockerfile -t t-fe ./frontend` + `docker build -f docker/Dockerfile.worker -t t-wk .` laufen durch.
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` valide (kein 'target development').
- `.secrets.baseline` hat gueltiges Schema (kein `{}`), `pre-commit run detect-secrets --all-files` PASS.
- `pip-audit` ist in dependencies.yml UND ci.yml ohne `|| true` aktiv.
- dependabot.yml docker-Block deckt `/`, `/frontend`, `/docker` ab.
- Alle Workflow-YAMLs syntaktisch valide (actionlint bzw. yaml.safe_load).
- Im Abschlussbericht: gewaehlte Release-Strategie begruenden + cross-Strom-Hinweise (Port 5433->5434, VERSION-Doku) auflisten.

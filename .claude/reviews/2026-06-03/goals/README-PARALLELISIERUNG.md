# Parallelisierung der /goal-Ströme — Ablage-System Remediation

**Kurzantwort:** **G1, G2, G3, G4 laufen komplett gleichzeitig** (Welle 1, je eigener git-worktree). **G5 läuft danach** (Welle 2), weil seine Tests den company_id-Fix aus G1 brauchen. Eine kleine **G0-Vorbereitung** geht voraus.

Belege: die Dateibäume der 5 Ströme sind **strikt disjunkt** (adversarial geprüft) — es gibt **kein einziges „file"-Konfliktpaar**, nur Interface-/Reihenfolge-Abstimmungen.

---

## Wellen

| Welle | Ströme | Gleichzeitig? | Bedingung |
|-------|--------|---------------|-----------|
| **0** | G0 (Config & Interface-Kontrakt) | — | klein, **vor** Welle 1 |
| **1** | **G1 · G2 · G3 · G4** | ✅ **alle 4 voll parallel** | je eigener worktree |
| **2** | G5 (Test-Wahrheit) | nach G1 (+G4) | Tests grün erst nach company_id-Fix |

## Konflikt-/Kopplungs-Matrix

```
        G1      G2      G3      G4      G5
 G1      —     none   iface   iface   iface
 G2    none     —     none    iface   iface
 G3    iface  none     —      none    none
 G4    iface  iface  none      —      iface
 G5    iface  iface  none    iface     —
```
- **none** = voll parallel, keine Abstimmung nötig.
- **iface** = kein gemeinsamer Datei-Pfad, nur Vertrag/Reihenfolge (z. B. G1 ruft G4-Service-Methode; G3 zeigt Empty-State bis G1-Endpoint da ist).
- **kein „file"-Konflikt** in der gesamten Matrix.

**Ohne jede Koordination gleichzeitig:** G2↔G3, G2↔G1, G3↔G4, G3↔G5.
**Gleichzeitig, aber Vertrag vorab fixieren (G0):** G1↔G4 (3 Punkte: KPI-Lesemethoden, Fraud-Modell, Restart-Hook).

## Disjunkte Dateibäume (= warum es konfliktfrei ist)

| Strom | Dateibaum |
|-------|-----------|
| G1 | `app/api/**` |
| G2 | `.github/**`, `docker/**`, `docker-compose*.yml`, `.secrets.baseline`, `.pre-commit-config.yaml`, `requirements*.txt`, `.releaserc.json` |
| G3 | `frontend/src/**` |
| G4 | `app/services/**`, `app/workers/**`, `app/db/**` |
| G5 | `tests/**`, `pytest.ini` |

> Die globalen Bottlenecks `app/db/models.py` und `app/workers/celery_app.py` liegen **exklusiv in G4** — kein anderer Strom fasst sie an.

## Liegt AUSSERHALB aller 5 Ströme (→ G0 bzw. Mini-PRs)
- `app/core/config.py` — Settings `FINTS_ALLOW_MOCK_SYNC`, `FINTS_AUTO_SYNC_ENABLED` (G4 liest defensiv via `getattr`).
- `requirements*.txt` — `asn1crypto`/`cryptography` für RFC-3161-TSA (G4).
- `alembic/env.py` → `from app.db.all_models import *` — **erst nach G4-Merge** (all_models.py liefert G4).
- `pyproject.toml` `fail_under=90` — Coverage-Gate-Anpassung (G5 meldet, G2/Config setzt um).

## Kritischer Pfad
```
G0 (Kontrakt) → G4 (Services/Modelle/Hooks) → G1 (API scharf) → G5 (Tests grün + Coverage)
```
G2 und G3 liegen **nicht** auf dem kritischen Pfad — jederzeit parallel mergebar, degradieren elegant.

## Merge-Reihenfolge
1. **G4** zuerst (liefert Service-Methoden, Fraud-Modell, Restart-Hook, `all_models.py`).
2. **G1** danach (verdrahtet G4-Interfaces, company_id scharf).
3. **G2 & G3** jederzeit (G2-CI-Guard erst nach G4 scharf stellen).
4. **G5** zuletzt.
5. Mini-PR: `alembic/env.py` → `all_models` (nach G4).

## Ausführung (git-worktrees)
```bash
# Welle 0
git worktree add ../ablage-g0 -b feature/g0-prereq master     # GOAL-G0 → /goal, mergen

# Welle 1 — 4 Sessions gleichzeitig
git worktree add ../ablage-g1 -b feature/g1-api-companyid master
git worktree add ../ablage-g2 -b feature/g2-cicd          master
git worktree add ../ablage-g3 -b feature/g3-frontend      master
git worktree add ../ablage-g4 -b feature/g4-services-db   master
# je Worktree eine Claude-Code-Session, /goal aus GOAL-G1..G4.md

# Merge G4 → G1 → (G2,G3), dann Welle 2
git worktree add ../ablage-g5 -b feature/g5-test-truth    master   # GOAL-G5 → /goal
```

## Goal-Dateien
| Datei | Strom | Welle | Aufwand |
|-------|-------|-------|---------|
| `GOAL-G0-vorbereitung.md` | Config & Kontrakt | 0 | S |
| `GOAL-G1-backend-api.md` | Backend-API (B1, M1-M6) | 1 | XL |
| `GOAL-G2-cicd-infra.md` | CI/CD + Infra (B3) | 1 | L |
| `GOAL-G3-frontend.md` | Frontend Mocks (M18-M23) | 1 | L |
| `GOAL-G4-services-db.md` | Services/Workers/DB (B2, M7-M17) | 1 | L |
| `GOAL-G5-tests.md` | Test-Wahrheit (B4) | 2 | XL |

Großer Gesamtplan (visuell): `../REMEDIATION_PLAN.html`

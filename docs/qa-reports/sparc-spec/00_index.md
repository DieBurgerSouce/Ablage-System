# SPARC Remediation-Spezifikation — Index (00)

**Branch:** `qa/az-deep-offensive-2026-06-18` · **Stand:** 2026-06-19 · **Modus:** spec-only (keine Code-Aenderungen)

## Zweck
Ehrliche, **agent-verifizierte** Spezifikation des TATSAECHLICHEN Remediation-Zustands des Ablage-Systems plus
Spec/Pseudocode/TDD-Anker fuer die ECHTE Restarbeit. Grund: Die vorangegangene Offensive hat viele Fixes
*behauptet*; eine unabhaengige Verifikation (3 Read-only-Explore-Agents) hat mehrere Behauptungen widerlegt.

## Leitprinzip
**Keine Aussage "behoben" ohne reproduzierbare Evidenz.** Jede Behebung gilt erst als erledigt, wenn ALLE drei
gelten: (1) Re-Test gruen, (2) `grep`-Residuen == 0, (3) Live-Endpoint 200/erwartet. Diese Spec dokumentiert nur
den belegten IST-Zustand + die Ziel-DoD — sie behauptet selbst nichts als "fertig".

## Status-Label-Legende
- **VERIFIZIERT-OK** — per Befehl/Test belegt funktionsfaehig.
- **RESIDUEN** — teilweise gefixt; belegte Rest-Vorkommen bleiben.
- **NICHT-BEHOBEN** — Fix nicht (wirksam) vorhanden.
- **PRE-EXISTING** — Defekt war vor der Session da, keine Session-Regression.
- **INFRA-DOWN** — Komponente aktuell nicht laufend.
- **LAUFZEIT-UNVERIFIZIERT** — Code vorhanden, Laufzeitverhalten nicht belegt.
- **NUR-BRANCH** — Fix existiert nur auf dem Branch, nicht auf master/Prod.

## Module
- `01_verified_state_matrix.md` — Behauptung vs. Realitaet (Evidenz je Punkt).
- `02_get500_truth_and_reverify_protocol.md` — GET-500-Realitaet + Re-Verifikations-Protokoll.
- `03_tenancy_residuals_spec.md` — 40 bare-getter + sso getattr.
- `04_phantom_columns_spec.md` — Document.metadata, User.company_id vs PortalUser.
- `05_enum_money_spec.md` — 16 Enum + 426 float() + Float->Numeric-Migration.
- `06_infra_spec.md` — health/startup 503, Beat/Worker down, WS-Token.
- `07_frontend_spec.md` — Token-Ablauf-Redirect, 13 Pfad-Fixes, ~80 Feature-Luecken.
- `08_master_merge_spec.md` — 2FA + SCAN nur Branch.
- `09_remaining_roadmap.md` — priorisierter Index mit TDD-Ankern.

## Methodik der Verifikation (reproduzierbar)
- GET-Sweep/Regression: `pytest tests/integration/test_get_endpoints_no_500.py` (BASE 127.0.0.1:8000).
- Residuen: `grep -rn <pattern> app/`.
- Infra: `docker inspect <container> --format '{{.State.Status}}/{{.State.Health.Status}}/{{.RestartCount}}'`.
- Live: `Invoke-WebRequest http://127.0.0.1:8000/api/v1/<pfad>` mit Bearer-Token.
- Quelle der Erst-Verifikation: 3 Explore-Agents (Runtime/Infra, Code-Residuen, Training-RootCause/Frontend/Open).
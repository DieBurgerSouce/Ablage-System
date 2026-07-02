# 09 — Priorisierte Rest-Roadmap (mit TDD-Ankern)

Reihenfolge nach Risiko/Wirkung. Jeder Punkt verweist auf das Detail-Modul. KEINE Aussage "behoben" ohne
das Re-Verifikations-Protokoll aus `02`.

## P0 — Produktion verwundbar / System degradiert
| ID | Punkt | Modul | DoD-Kurz |
|----|-------|-------|----------|
| P0-1 | 2FA-Bypass + SCAN-Cursor nach master | 08 | master enthaelt Commits; rbac TESTING; SCAN terminiert |
| P0-2 | Beat/Worker/Worker-CPU EXITED hochfahren + Boot-Fehler fixen | 06/I2 | running+healthy; inspect ping ok |
| P0-3 | /health/startup 503 (REDIS_URL reconcile) | 06/I1 | Live 200, checks.redis true |
| P0-4 | WS-Token im URL | 06/I3 | kein ?token= ; Realtime ok |
| P0-5 | /training/* 500 + Diskrepanz klaeren | 02 | kein 5xx; Ursache der frueheren "0" belegt |

## P1 — Korrektheit / Tenancy / latente Datenfehler
| ID | Punkt | Modul | DoD-Kurz |
|----|-------|-------|----------|
| P1-1 | 40 bare-getter Tenancy-Residuen + sso getattr | 03 | grep=0 (ausser portal); MT-Isolationstest gruen |
| P1-2 | Document.metadata (12, ocr.py) | 04 | grep=0; OCR-Endpunkte 200 |
| P1-3 | 16 Enum values_callable (DB-verifiziert je Spalte) | 05/T1 | Roundtrip-Test gruen; budget unveraendert |
| P1-4 | Money: Float->Numeric-Migration + Decimal-Disziplin | 05/T2 | Spalten Numeric; net+vat==gross Property-Test |

## P2 — Feature-Vollstaendigkeit / UX / Hardening
| ID | Punkt | Modul | DoD-Kurz |
|----|-------|-------|----------|
| P2-1 | Token-Ablauf-Redirect Real-401-E2E | 07/F1 | E2E gruen (echter 401 -> /login) |
| P2-2 | ~80 Frontend-Feature-Luecken (Entscheidungs-Matrix) | 07/F3 | je Cluster implement/remove/roadmap entschieden |
| P2-3 | 426 float() Consumer-Layer (nach P1-4) | 05/T2 | kein float() als Speicher-Zwischenschritt |
| P2-4 | Route-Guards (beforeLoad) / Token-Storage | 07/F4 | optional, separater Track |

## Querschnitt-Regeln (verbindlich)
- Jede Behebung: Re-Verifikations-Protokoll (02) — Test gruen + grep=0 + Live-200 + nach Restart stabil.
- Status-Pflege: `01_verified_state_matrix.md` nach jeder belegten Behebung aktualisieren (mit Evidenz).
- Branch-Disziplin: alles auf `qa/az-deep-offensive-2026-06-18`; master-Merge nur per `08` koordiniert.
- KEINE "fertig"-Behauptung ohne Evidenz (Kernanweisung des Nutzers).

## Quellen
- Verifikation: 3 Read-only-Explore-Agents (2026-06-19).
- Belege/Findings: `docs/qa-reports/2026-06-19-wave1-master-findings.md`, `..._explore-register.md`,
  `tests/integration/test_get_endpoints_no_500.py`.
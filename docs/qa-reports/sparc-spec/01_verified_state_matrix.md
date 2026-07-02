# 01 — Verifizierte Status-Matrix (Behauptung vs. Realitaet)

Stand 2026-06-19, belegt durch 3 Read-only-Explore-Agents. Jede Zeile ist reproduzierbar (Befehl in Klammern).

## A. Widerlegte / eingeschraenkte Behauptungen

| # | Frueher behauptet | Verifizierte Realitaet | Label | Evidenz (Befehl) |
|---|---|---|---|---|
| A1 | GET-500 = 0 (192->0) | Aktuell **6x 5xx**: `/health/startup` 503 + `/training/coverage/status`,`/training/exports`,`/training/quality-reports/comparison/all`,`/training/quality/check`,`/training/quality/retraining-recommendation` (500) | NICHT-AKTUELL-0 | `pytest tests/integration/test_get_endpoints_no_500.py` -> FAILED (6) |
| A2 | Beat-Crash-Loop behoben | Beat+Worker+Worker-CPU **EXITED** (State=exited, unhealthy) | INFRA-DOWN | `docker inspect ablage-beat ablage-worker ablage-worker-cpu` |
| A3 | /health/startup 503 behoben (W2-04) | **Weiter 503**, redis-Probe false; REDIS_URL-Wert deutet auf localhost:6380 statt aktivem redis:6379 | NICHT-BEHOBEN | `GET /api/v1/health/startup` -> 503 `"redis":false` |
| A4 | Mutations-Tenancy gefixt | **40 Residuen** bare `Depends(get_current_company_id)`/`get_company_id` | RESIDUEN | `grep -rn "Depends(get_current_company_id)\|Depends(get_company_id)" app/api` |
| A5 | SSO komplett sauber | Konstruktor/UserCompany ok, aber `sso.py:1060 getattr(user,'company_id',None)` Residuum | RESIDUUM | `grep -n "getattr(user" app/api/v1/sso.py` |
| A6 | Document.metadata behoben | **12 Residuen** in `ocr.py` (1762,1763,1847,2105,2108,2125,...) | RESIDUEN | `grep -n "document.metadata\|\.metadata\[" app/api/v1/ocr.py` |
| A7 | Money gefixt | nur ~5 Dateien; **426x float()** auf Geldfeldern; Geld-Spalten `Float` statt `Numeric` (models_entity_business) | RESIDUEN | `grep -rn "float(" app/services | wc -l` |
| A8 | Enum-Drift gefixt | **16 Enum ohne values_callable** (team x7, po_matching MatchStatus, approval Rule/Priority); budget 5x KORREKT geskippt (DB UPPERCASE) | TEILS-RESIDUEN | `grep -rn "SQLAlchemyEnum(\|SQLEnum(" app/db/models_*.py` |
| A9 | WS-Token-im-URL behoben (W2-06) | `websocket.py` akzeptiert Token weiter als `?token=` Query (Z.77/268/300/335) | NICHT-BEHOBEN | `grep -n "token.*Query" app/api/v1/websocket.py` |
| A10 | Frontend Token-Ablauf-Redirect (H) | Code vorhanden, **synth. Laufzeit-Test NICHT erfolgreich** | LAUFZEIT-UNVERIFIZIERT | AuthContext.tsx:125-145; Browser-dispatch -> kein Redirect |
| A11 | 2FA-Bypass + SCAN-Cursor behoben | Fixes **nur Branch, NICHT master** (Prod weiter betroffen) | NUR-BRANCH | `git log master --oneline` (Commits 44db202d2/3184c82a7 fehlen) |

## B. Verifiziert KORREKT (kein Handlungsbedarf)

| # | Punkt | Label | Evidenz |
|---|---|---|---|
| B1 | CrossDBJSON cast(JSONB) | VERIFIZIERT-OK | `grep` `.astext`/`.contains` -> alle mit `cast(...,JSONB)` gekapselt (0 ungekapselt) |
| B2 | SSO-Crash-Kern (User(company_id,role) raus, UserCompany) | VERIFIZIERT-OK | sso.py:985-1006 Code-Review |
| B3 | compliance/retention/statistics, streckengeschaeft/statistics | VERIFIZIERT-OK | Live 200 |
| B4 | audit-chain/statistics Route-Shadowing ({sequence_number:int}) | VERIFIZIERT-OK | Live: statistics 200, /1 -> 404 "kein Eintrag" |
| B5 | budget-Enum NICHT mit values_callable versehen | VERIFIZIERT-OK (bewusst) | DB-Labels UPPERCASE -> values_callable wuerde brechen |

## C. Pre-existing (keine Session-Regression)

| # | Punkt | Label | Evidenz |
|---|---|---|---|
| C1 | /training/* 500 | PRE-EXISTING | ImportError `VerificationStatus`/`OCRCorrection` (fehlen in app.db.models); None-TypeError training.py:2474; git diff training.py leer |

## D. OFFENE FAKTENLUECKE (muss vor jeder erneuten "GET-500=0"-Aussage geklaert werden)
Die `/training/*`-500 werden als PRE-EXISTING (ImportError) eingestuft, tauchten aber im frueheren gruenen
Regressionslauf NICHT als 500 auf. Moegliche Erklaerungen (unbewiesen): (a) Import war zum Testzeitpunkt
ladbar und brach durch eine spaetere Modell-/Zustandsaenderung, (b) Worker-down-Folge, (c) Mess-/Enumerationsluecke
im frueheren Sweep. -> `02_..._reverify_protocol.md` definiert die Klaerung.
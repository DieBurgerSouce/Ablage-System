# Mock-/Fake-Data-Register — Ablage-System

**Erstellt**: 2026-06-03
**Zweck**: Vollständige, belegte Inventur aller Stellen, die **Mock-/Platzhalter-/Stub-Daten als echt** ausgeben oder Aktionen vortäuschen, die nicht persistieren.
**Basis**: Fan-Out-Status-Scan (12 Subagents) + Stichproben-Verifikation gegen den Code am 2026-06-03.
**Status dieser Phase**: NUR Dokumentation. Kein Code wurde geändert. Dieses Register ist die Grundlage der späteren „Mocks → echt"-Kampagne (siehe Anschluss-Roadmap unten).

> **STATUS-UPDATE 2026-06-04 (Mocks→echt Phase 1):** Die meisten Backend-Mocks sind behoben: **M1/M2/M4/M5** (Dashboard-KPIs/Fraud-Alerts echt, G1), **M3/M6** ehrlich (None bzw. 501 statt Fake; echte Daten/Restart als Kontrakt), **M7/M8** OUTSCOPED (PSD2/BaFin), **M9** geguarded (G4), **M10–M13** echt bzw. ehrlich `is_estimated` (G4), **M14** RFC-3161 via asn1crypto (G4), **M15** company-scoped + ehrlich (G4), **M16** autonome Folder-Ablage AKTIVIERT (2026-06-04, `feature/mocks-to-real-p1`). **Kein Mock zeigt mehr erfundene Daten als echt.** OFFEN als ehrlich gekennzeichnete Feature-Tiefe (keine Luege): **M13** echter Backtest (Prediction-Snapshots, braucht Migration), **M17** BPMN Subprocess/Signal/Repeating-Timer (Engine-Feature).

> ⚠️ **Kernaussage**: Mehrere als „Production-Ready" dokumentierte Features zeigen dem Nutzer **erfundene Daten als echt** oder lösen Aktionen aus, die keine Wirkung haben. Das ist der Hauptgrund, warum der reale Reifegrad unter dem dokumentierten liegt.

Legende Aufwand: **S** ≤0,5 Tag · **M** ~1-2 Tage · **L** ~3-5 Tage · **XL** >1 Woche / externe Abhängigkeit.

---

## A) Backend — KPIs & Endpoint-Stubs, die als echt erscheinen

| # | Stelle | Datei:Zeile | Befund (verifiziert) | Bewusst vertagt? | Real-Wiring | Aufwand |
|---|--------|-------------|----------------------|------------------|-------------|---------|
| **M1** | Dashboard Cash-Flow-KPIs | `app/api/v1/dashboard.py:649, 753-754` | „Cash Flow KPIs (simplified - would integrate with banking service)"; „For now, return placeholder values" → liefert 0/`stable` | Nein (unfertig) | An Banking-/Skonto-Service anbinden (`banking/skonto_service.py`) | M |
| **M2** | Dashboard Approval-KPIs | `app/api/v1/dashboard.py:828-829` | „This would integrate with the approval service / For now, return placeholder values" → liefert 0 | Nein (unfertig) | An Approval-Service anbinden | M |
| **M3** | Dashboard OCR-Quality-KPIs | `app/api/v1/dashboard.py:858-860` | hardcoded `success_rate=95.5`, `avg_confidence=0.87`, `manual_corrections=0` (alle `# Placeholder`) | Nein (unfertig) | An OCR-/Self-Learning-Service anbinden | M |
| **M4** | Dashboard `avg_payment_days` | `app/api/v1/dashboard.py:729` | `avg_payment_days = 14.5  # Placeholder - would calculate from actual data` | Nein (unfertig) | Aus `InvoiceTracking` real berechnen | S |
| **M5** | Fraud-Alert Detail/Aktionen | `app/api/v1/fraud_detection.py:260-262, 282-284` | `GET /alerts/{id}` + `POST /alerts/{id}/action` werfen 501 „noch nicht implementiert"; Alerts werden nicht persistiert | Teils (sauber als 501) | Alert-Persistenz + Aktionen umsetzen ODER Endpoints aus Router entfernen | M |
| **M6** | Admin Service-Restart | `app/api/v1/admin/system.py:244-275` | „For now, return a placeholder response" — meldet Neustart, ohne ihn auszuführen | Nein | Echte Celery-Restart-Logik ODER Antwort als Dry-Run kennzeichnen | S |

## B) Backend Services — Mock/vereinfacht im Produktionspfad

| # | Stelle | Datei:Zeile | Befund (verifiziert) | Bewusst vertagt? | Real-Wiring | Aufwand |
|---|--------|-------------|----------------------|------------------|-------------|---------|
| **M7** | Auto-Bankimport FinTS | `app/services/banking/auto_transaction_import_service.py:468, 480` | „For development: Generate mock data"; „Mock: Return empty for now" → `_fetch_fints_transactions` liefert `[]` | **Ja** — PSD2/FinTS-Auto-Sync ist in `breezy-napping-hare.md` als „OUTSCOPED (BaFin-Compliance)" markiert | Echte FinTS-Anbindung ODER Feature klar als deaktiviert kennzeichnen | XL |
| **M8** | Auto-Bankimport PSD2 | `app/services/banking/auto_transaction_import_service.py:434, 590` | `access_token="placeholder"  # Would come from encrypted token` statt echtem Token | **Ja** (s. M7) | Echte Token-Entschlüsselung/OAuth2 | XL |
| **M9** | enhanced_fints Sync | `app/services/banking/enhanced_fints_service.py:667-669, 1187` | „In Produktion: Echte FinTS-Transaktion / Hier: Mock-Daten" → `_generate_mock_transactions()` durchläuft echte Reconciliation/Buchung | **Teilweise** — Mock gewollt, aber Auswirkung auf echte Buchungen ist es NICHT | Mock-Pfad darf keine echte Reconciliation/Postings auslösen (Feature-Flag/Guard) | M |
| **M10** | Fraud-Detection (3 Methoden) | `app/services/ai/fraud_detection_service.py:556-558, 585-586, 625-626` | `detect_self_approval` „return empty result as placeholder"; `detect_unusual_approval_pattern`, `analyze_audit_trail` = leere Indikatorlisten | Nein | An Approval-/Audit-Tabellen anbinden ODER mit Warn-Log/Feature-Flag versehen | L |
| **M11** | Explainable-Anomaly-Statistiken | `app/services/ai/explainable_anomaly_service.py:402-415, 459-480` | hardcoded `occurrences_30d=5, occurrences_90d=15, similar_cases_count=5` in Erklärungen | Nein | Durch echte DB-Statistiken ersetzen | M |
| **M12** | Auto-Booking Confidence | `app/services/accounting/gl_posting_service.py:414` | `confidence=0.85  # Placeholder` direkt vor `post_journal_entry` | Nein | Echten Extraktions-Confidence durchreichen | S |
| **M13** | Cashflow-Genauigkeit | `app/services/ai/cashflow_prediction_service.py:563-599` | „Vereinfachte Schätzung" statt Vergleich gespeicherter Predictions mit Ist | Nein | Prediction-Snapshots speichern und vergleichen | M |
| **M14** | RFC-3161-TSA-Zeitstempel | `app/services/compliance/tsa_service.py:578-630` | handgebautes ASN.1, explizit „nicht vollständig RFC-konform" — **GoBD-Risiko** | Nein | RFC-3161 über geprüfte Lib (`cryptography`/`asn1crypto`) | M |
| **M15** | GoBD-Checks (vereinfacht) | `app/services/compliance/gobd_service.py:250, 409, 567, 799` | mehrere Prüfungen „simplified – in production would …" | Nein | Sequenz-/Berechtigungs-/Aggregations-Checks vervollständigen | M |
| **M16** | Autonome Ordner-Ablage | `app/services/ai/autonomous_actions_service.py:39-42` | `Folder = None  # Placeholder` — Filing in Ordner deaktiviert (Modell fehlt) | Teils (dokumentiert) | Folder-Datenmodell ergänzen ODER als deaktiviert führen | M |
| **M17** | BPMN-Subprocess | `app/services/bpmn/process_execution_service.py:262, 861, 932` | „Vereinfachte Implementierung — vollständig würde eigene Sub-Instanz benötigen" | Teils | Vollständige Subprocess-/Multi-Instance-Ausführung | L |

## C) Frontend — `Math.random`/Mock als echte UI

| # | Stelle | Datei:Zeile | Befund (verifiziert) | Bewusst vertagt? | Real-Wiring | Aufwand |
|---|--------|-------------|----------------------|------------------|-------------|---------|
| **M18** | Knowledge-Graph (3/4 Tabs) | `frontend/src/features/knowledge-graph/views/RiskNetworkView.tsx:189, 298, 301` (analog `FinancialChainView.tsx`, `DocumentFamilyView.tsx`) | lokale Hooks geben `generateMock*()` zurück und melden fest `isLoading: false, error: null`; **echte Hooks `useRiskNetwork/useFinancialChain/useDocumentFamily` existieren ungenutzt** | Nein | Views auf vorhandene echte Hooks umstellen, `generateMock*` entfernen | M |
| **M19** | Streckengeschäft-Validierung | `frontend/src/app/routes/streckengeschaeft.validierung.tsx:27-98, 102` | `useState(mockData)` mit 6 hartkodierten 2024er-`ValidationItem`s; Approve/Reject ändert nur lokalen State, **keine Persistenz** (USt-relevant!) | Nein | Liste per `useQuery` laden, Aktionen per `useMutation` persistieren | M |
| **M20** | Reports stiller Fallback | `frontend/src/features/reports/api/report-data-api.ts:106-139` | bei 404 synthetische Report-Daten (`_getFallbackData`), nur `logger.warn` — Nutzer sieht keinen Hinweis | Nein | Backend-Endpunkte umsetzen ODER sichtbarer Empty-State + Telemetrie | M |
| **M21** | Import-Wizard-Vorschau | `frontend/src/features/import-wizard/api/wizard-api.ts:117-141, 147-180` | 404 → Mock `{itemCount:0, warnings:['Vorschau-Funktion noch nicht verfügbar']}` täuscht Vorschau vor | Teils (gewarnt) | Preview-Endpunkte umsetzen | S |
| **M22** | Massen-Statusupdate (Ablage) | `frontend/src/features/ablage/components/StatusChangeDropdown.tsx:115-138` | nur Status „bezahlt" verkabelt; andere → `logger.warn` „noch nicht implementiert", aber `onSuccess()` läuft trotzdem → **falscher Erfolgseindruck** | Nein | restliche Status verkabeln ODER nicht unterstützte Status deaktivieren | S |
| **M23** | Job-Queue-Charts | `frontend/src/features/job-queue/components/charts/SuccessRateChart.tsx:44-124` (analog `QueueLengthChart`, `JobThroughputChart`) | `generateMockData()` mit `Math.random` als Default (`return data || generateMockData()`) | Nein | Mock-Default entfernen, Empty-State | S |

---

## Anschluss-Roadmap „Mocks → echt" (separate Folge-Phase, NICHT in dieser Phase)
Priorisiert nach Nutzer-Primärziel **Feature-Wahrheit**:

1. **Frontend (sichtbarster Impact)**: M18, M19, M20, M21, M22, M23
2. **Backend-KPIs/Fraud**: M1-M4 (Dashboard an echte Services), M10 (Fraud-Detection), M5 (Fraud-Alerts persistieren)
3. **Banking ehrlich**: M7-M9 — PSD2 ist bewusst OUTSCOPED → klar kennzeichnen; **M9 zuerst absichern** (kein Mock-Sync in echte Reconciliation/Buchung)
4. **Compliance-Wahrheit**: M14 (RFC-3161), M15 (GoBD), M11/M13 (echte Statistiken)
5. **Aufräumen**: M6 (Admin-Restart), M12 (Confidence), M16/M17

## Sofort-Risiko-Hinweis (auch wenn Fix später kommt)
- **M9** ist das gefährlichste Mock: generierte Fake-Transaktionen durchlaufen echte Auto-Reconciliation und können echte Buchungen auslösen. Bis zum Fix sollte der Auto-Sync-Beat deaktiviert oder hinter einem Feature-Flag stehen.
- **M14/M15** sind Compliance-Risiken (GoBD/Revisionssicherheit), die als „Production-Ready" vermarktet werden, aber nicht garantiert konform sind.

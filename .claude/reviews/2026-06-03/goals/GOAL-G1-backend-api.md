<!--
/goal-Prompt — Strom G1: Backend-API (company_id-Rollout, Dashboard-KPIs, Fraud-Alerts, Restart)
WELLE 1 — laeuft parallel mit G2, G3, G4. Worktree/Branch: feature/g1-api-companyid
Abhaengigkeit: G0 (Interface-Kontrakt) vorab; konsumiert G4-Service-Methoden (Merge G4 -> G1).
Den Text ab "===" als /goal in eine Claude-Code-Session einfügen.
-->

=== GOAL G1 ===

Du arbeitest ausschliesslich im Dateibaum **app/api/** des Projekts Ablage-System (FastAPI/Python-Backend, Repo-Root C:\Users\benfi\Ablage_System). Andere Verzeichnisse (app/db, app/services, app/middleware, frontend) darfst du NUR LESEN, nicht editieren - DB-Modelle, Services und Migrationen gehoeren zu anderen Stroemen.

## Ziel
Multi-Tenant-Sicherheit der REST-API haerten und vier funktionale Luecken im API-Layer schliessen.

## Scope-Grenze (HART)
- Editieren erlaubt: NUR Dateien unter `app/api/**` (inkl. `app/api/dependencies.py`, `app/api/v1/**`, `app/api/v1/admin/**`, `app/api/v1/banking/**`, `app/api/v1/portal/**`).
- KEIN Anlegen/Aendern von DB-Modellen, Alembic-Migrationen oder Services. Wenn eine Service-/Modell-Methode fehlt: als Cross-Stream-Dependency zu G4 dokumentieren (Kommentar `# TODO(G4): ...`) und im API-Layer einen ehrlichen Fallback liefern (None/403/404/501), NIEMALS erfundene Zahlen.

## Aufgaben (in dieser Reihenfolge)

### 1. B1 (CRITICAL) - get_user_company_id_dep zentralisieren
Die Helfer `get_user_company_id`, `_require_user_company_id`, `get_user_company_id_dep` sind aktuell nur lokal in `app/api/v1/invoices.py` (Zeilen 45-103) definiert. Verschiebe sie nach `app/api/dependencies.py` (zentraler Import-Ort, den fast alle Endpoints bereits nutzen). UserCompany/Company-Query exakt uebernehmen (is_current=True, Company.is_active, deleted_at IS NULL, Fallback erste Firma). 403-Meldung "Kein Unternehmen zugeordnet" beibehalten. In `invoices.py` durch `from app.api.dependencies import get_user_company_id, get_user_company_id_dep` ersetzen (Re-Export). **User-Modell NICHT anfassen.**

### 2. B1 - company_id-Rollout (821 Vorkommen, 95 Dateien)
Ersetze alle `current_user.company_id` in `app/api/**` durch das auth-gebundene Dependency-Pattern. Pro Endpoint-Funktion:
- Signatur ergaenzen: `company_id: UUID = Depends(get_user_company_id_dep)` (nach current_user/db).
- Import ergaenzen: `from app.api.dependencies import get_user_company_id_dep`.
- Im Koerper jedes `current_user.company_id` -> `company_id` (auch in `Model.company_id == current_user.company_id` und `company_id=current_user.company_id`).
- Helper-/Background-Funktionen ohne Request-Kontext: `company_id` explizit als Parameter durchreichen.
- Lokale `async def get_user_company_id(db, user)` Definitionen (ai_autonomy.py, autonomous.py, workflows.py) auf die shared Variante umstellen.
- **NICHT** ersetzen: legitime Model-Attribut-Zugriffe ohne `current_user.`-Praefix (z.B. `doc.company_id`).
- **Vorsicht** bei Superuser-/Cross-Company-Endpoints (cross_tenant_reports.py, holding.py, companies.py, admin/*): pruefen ob `validate_company_access`/Superuser-Logik erhalten bleiben muss, statt blind auf eine einzelne company_id zu zwingen.

Strategie: codemod-artig in Teil-Batches (zuerst dichte Files >=20 Treffer: compliance.py, approvals.py, approval_matrix.py, bpmn.py, fraud.py, process_mining.py, approval_enhanced.py, datev_connect.py, validation.py, delegations.py; dann je 10-15 Files). Nach jedem Batch: `ruff check` + `mypy` + relevante `pytest`.

### 3. M1-M4 Dashboard-KPIs (`app/api/v1/dashboard.py`)
- Zeile 728-729 `_get_invoice_kpis`: `avg_payment_days = 14.5` ersetzen durch echte SQL-Aggregation auf InvoiceTracking (paid_at, due_date/invoice_date vorhanden), company-gefiltert; 0 Rows -> 0.0.
- Zeile 751-761 `_get_cash_flow_kpis`: Platzhalter (0.0/stable) durch `CashFlowService` (app/services/banking/cash_flow_service.py, Methoden get_cash_flow_summary/get_cash_flow_forecast) ersetzen; Trend aus net_cash_flow ableiten; try/except + logger.warning + 0.0-Fallback (kein HTTP-500).
- Zeile 824-835 `_get_approval_kpis`: Platzhalter durch DB-Queries auf ApprovalRequest/ApprovalStep (app/db/models_privat_enterprise.py) ersetzen (Muster wie _get_alert_kpis). Fehlt company_id-Spalte/Service-Methode -> `# TODO(G4)` + konservativ 0.
- Zeile 858-860 `_get_ocr_quality_kpis`: `success_rate=95.5`, `avg_confidence=0.87`, `manual_corrections=0` durch OCRQualityMetricsService-Werte ersetzen. Bietet der Service keine company-gefilterte persistente Lese-Methode -> `# TODO(G4)` + None/klar gekennzeichnet statt erfundener Zahl.
Alle Platzhalter-Kommentare entfernen.

### 4. M5 Fraud-Alerts (`app/api/v1/fraud_detection.py:248-285`)
`get_fraud_alert_detail` und `take_alert_action` werfen aktuell HTTP 501. Implementiere Lesen eines persistierten Alerts (company-gefiltert, 404 "Alert nicht gefunden" wenn fehlt) und Aktionen (dismiss/investigate/escalate/false_positive) mit Statuspersistenz. Erfordert ein Fraud-Alert-DB-Modell -> NICHT anlegen, als `# TODO(G4)` dokumentieren. Falls das vorhandene `Alert`-Modell (app/db/models_alert.py) fachlich passt, dagegen verdrahten; sonst ehrlicher 404/409 statt 501. Keine PII loggen.

### 5. M6 Restart (`app/api/v1/admin/system.py:244-275`)
Den "In a real implementation..."-Platzhalter ersetzen: echten Celery-Restart anstossen falls Infrastruktur vorhanden, sonst ehrlichen HTTP 501/503 mit deutscher Meldung "Automatischer Neustart in dieser Umgebung nicht unterstuetzt" statt faelschlich erfolgreicher MessageResponse. Superuser-Guard beibehalten.

## Constraints
- ALLE user-facing Texte DEUTSCH (UTF-8, Umlaute korrekt).
- Type Safety: mypy strict, KEIN `Any`. Alle neuen Signaturen/Returns typisiert.
- Kein PII-Logging (Rule 1/8): keine Kundennummern, IBANs, USt-IDs, keine sensiblen Inhalte in Logs.
- Keine HTTP-500/AttributeError bei fehlender company_id -> sauberer 403.
- Performance-Target API <500ms beachten (aggregierte Queries, kein N+1).
- Tests muessen vor Abschluss gruen sein.
- Keine neuen Dateien im Root; keine *.md-Reports anlegen.

## Definition of Done
1. `rg -n "current_user\.company_id" app/api` -> 0 Treffer (auch Docstrings bereinigt).
2. `ruff check app/api` und `mypy app/api` (strict) ohne Fehler.
3. `pytest tests/ -k "api or dashboard or fraud or approval or compliance"` gruen.
4. Dashboard liefert echte oder klar als nicht-verfuegbar gekennzeichnete Werte (keine 14.5/95.5/0.87/0.0-Platzhalter mehr).
5. fraud_detection /alerts/{id} und /action liefern 200/404/409 statt 501.
6. admin restart_service liefert ehrliches Ergebnis (echter Restart oder 501/503), keinen Fake-Erfolg.
7. Stichprobe: migrierter Endpoint ohne UserCompany-Zuordnung -> HTTP 403 "Kein Unternehmen zugeordnet".

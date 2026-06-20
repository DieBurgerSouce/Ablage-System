# Manifest w3b-backend-sweep (Branch fix/w3b-backend-sweep, Worktree w2-services)

Stand: 2026-06-12. Alle 4 Queue-Items umgesetzt (5 Commits, Basis fix/w3-backend).
Hier TABU-Wuensche, Befunde ausserhalb der Queue und Merge-Hinweise.

## Merge-Hinweis: 6 Testdateien von fix/w3-tests uebernommen und veraendert

Fuer Queue-Item 2+4 wurden diese Dateien per `git checkout fix/w3-tests -- ...`
auf fix/w3b-backend-sweep geholt und dort die strict-xfail-Marker entfernt
(App-Bugs sind gefixt, Tests gruen OHNE xfail):

- tests/unit/services/test_compliance_autopilot_service.py
- tests/integration/test_ocr_pipeline_integration.py
- tests/unit/services/external/test_handelsregister_integration.py
- tests/unit/services/external/test_vies_integration.py (+ 1 Test umgedreht,
  der den Nicht-EU-Bug kodifizierte; + 1 neuer EU-Fallback-Test)
- tests/unit/services/test_enrichment_service.py (+ test_enrichment_updates_metadata
  in ehrlichen Vertrag umgeschrieben, siehe Befund 3)
- tests/integration/test_user_lifecycle_integration.py (test_very_long_password
  = echter Vertragstest, deutscher 72-Bytes-ValueError)

Beim Merge von fix/w3-tests und fix/w3b-backend-sweep gewinnen in diesen
Dateien die Versionen von fix/w3b-backend-sweep (xfail-frei + App-Fix).

## TABU-Wunsch 1: Router-Doppelregistrierungen (app/main.py)

Die 8 Duplicate-Operation-IDs sind via expliziter operation_id entschaerft
(app.openapi() = 0 Warnungen), aber die zugrunde liegenden PFAD-Doppel-
registrierungen (tote Routen, es gewinnt der zuerst inkludierte Router)
bestehen weiter und brauchen eine Router-Entscheidung in app/main.py:

- POST /api/v1/banking/payments/{id}/approve|cancel: banking/payments.py vs. banking/connections.py
- GET /api/v1/cashflow/summary: banking_fints.py vs. cashflow.py
- GET /api/v1/ocr-templates/candidates: ocr_templates.py vs. supplier_ocr_templates.py
- POST /api/v1/entities/{id}/verify: entities.py vs. supplier_verification.py
- DELETE /api/v1/annotations/{id}: annotations.py vs. _enhanced.py vs. _extended.py (3x!)
- POST /api/v1/annotations/threads/{id}/replies: _enhanced.py vs. _extended.py

Analog zu Befund 1 im Manifest w3-backend (Dashboards).

## Befund 2 (gross, eigener Folgeauftrag): BankTransaction-Spalten-Drift

Gleiche Bug-Klasse wie der InvoiceTracking-Sweep: `BankTransaction` hat
weder `company_id` noch `matched_invoice_id` (Modell models_banking.py:293;
echte Spalten: bank_account_id, matched_document_id, matched_invoice_number,
reconciliation_status). 18 Verwendungen in 11 Dateien, u. a.:

- BankTransaction.company_id (Query -> AttributeError/500): banking/
  liquidity_forecast_service.py:606, banking/smart_reconciliation_service.py:598,
  company_metrics_service.py:650, compliance/tax_authority_export_service.py,
  holding/holding_kpi_service.py (Banking-Metriken-Teil), holding/
  intercompany_reconciliation_service.py, insights/cashflow_predictor.py,
  insights/skonto_optimizer.py, knowledge_graph/graph_service.py,
  orchestration/anomaly_investigation_service.py, orchestration/
  seasonal_detector_service.py
- tx.matched_invoice_id (Instanz-Schreibzugriff, persistiert NICHT):
  banking/auto_reconciliation_service.py:207/729/947 — ACHTUNG: dieser
  Service gilt laut Memory als produktiv verifiziert; die Migration 203
  legt matched_invoice_id auf `imported_transactions` (PSD2) an, NICHT
  auf bank_transactions. Vor einem Fix klaeren, ob hier eigentlich
  ImportedTransaction gemeint ist oder das Modell der DB hinterherhinkt
  (F4-Pattern). Eigene Untersuchung noetig, NICHT mechanisch sweepen.

In den von w3b angefassten Dateien wurde nur app/services/ai/
action_executor_service.py umgestellt (BankAccount-JOIN + matched_document_id).

## Befund 3: Enrichment-Persistenz fehlt (Schema-Gap)

BusinessEntity hat KEINE metadata-/JSONB-Spalte; der alte Code
`entity.metadata["enrichment"] = ...` in enrichment_orchestrator.py crashte
auf echten ORM-Objekten mit TypeError (SQLAlchemy MetaData-Registry).
Kaputter Persist-Block entfernt — Enrichment-Ergebnisse werden aktuell NUR
zurueckgegeben, nirgends gespeichert. Followup: Schema-Erweiterung
(Satellit oder JSONB-Spalte via Migration, TABU fuer w3b) + Persist.

## Befund 4: Restliche InvoiceTracking-Phantome ausserhalb der Queue

Nach dem Sweep verbleiben (bewusst nicht angefasst, eigene Verifikation noetig):

- banking/smart_reconciliation_service.py:613/614 (is_paid/is_outgoing in Query)
  + gross_amount-Instanz-Zugriffe (348/418/477) + BankTransaction.company_id (598)
- orchestration/seasonal_detector_service.py:371/373 (InvoiceTracking.gross_amount
  als Spalte -> Query crasht)
- orchestration/anomaly_investigation_service.py:501/510, portal/
  portal_invoice_service.py, portal/portal_payment_service.py: `inv.gross_amount`-
  Instanz-Zugriffe (pruefen, ob inv wirklich InvoiceTracking ist)
- insights/cashflow_predictor.py:762/788/797/949: `inv.is_incoming` auf
  Instanz-Ebene -> braucht per-Row-Richtungsableitung (JOIN/Map), kein
  mechanischer Filter-Ersatz

Grep-Abnahme der Queue (InvoiceTracking.invoice_type|total_amount|
business_entity_id) ist 0 in app/.

## Befund 5: Pre-existing Failures (fuer w3-tests-Followup, auf fix/w3-backend identisch)

- tests/unit/services/dashboard/test_dso_tracker_service.py (Label 'nicht_faellig' vs 'Nicht faellig')
- tests/unit/services/dashboard/test_sharing_service.py (2x Count-Asserts)
- tests/unit/services/test_ceo_dashboard_service.py::test_digital_twin_anomalies
- tests/unit/services/test_company_metrics_service.py (2x: Umlaut-Label, Alerts)
- tests/unit/services/test_ocr_pipeline.py (3x structlog-Mock-TypeError)
- tests/unit/services/external/test_supplier_verification_service.py (2x: Score, Multi-Tenant)

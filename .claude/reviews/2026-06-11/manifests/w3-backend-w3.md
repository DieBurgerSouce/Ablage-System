# Manifest w3-backend (Branch fix/w3-backend, Worktree w2-services)

Stand: 2026-06-12. Alle 10 Queue-Items umgesetzt (10 Commits). Hier nur
TABU-Wuensche und Befunde ausserhalb der w3-backend-Zone.

## TABU-Wunsch 1: Router-Doppelregistrierung /api/v1/dashboards (main.py)

`app/api/v1/dashboards.py` und `app/api/v1/dashboard_builder.py`
registrieren teils IDENTISCHE Pfade (GET/POST `/api/v1/dashboards`,
GET/DELETE `/{dashboard_id}`, POST `/{dashboard_id}/share`,
POST `/{dashboard_id}/widgets`, DELETE `/{dashboard_id}/widgets/{widget_id}`).
Es gewinnt der zuerst in main.py inkludierte Router; die zweite
Registrierung ist TOTE Route (wird nie bedient). w3-backend hat die
OpenAPI-Operation-ID-Kollisionen via expliziter `operation_id`
(builder_-Praefix) entschaerft (Commit a39a57fc4), aber die
Doppelregistrierung selbst braucht eine Router-Entscheidung in
app/main.py (TABU): einen der beiden Router umziehen (z.B.
`/dashboard-builder`-Prefix) oder konsolidieren.

## Befund 2 (gross, eigener Folgeauftrag): invoice_type/total_amount-Drift in weiteren Services

w3-backend hat die 3 beauftragten AI-Services auf Entity-JOIN-Ableitung
umgestellt (Helper: `app/services/invoice_direction.py`,
`is_outgoing_invoice()`/`is_incoming_invoice()`). DERSELBE latente
AttributeError-500 (InvoiceTracking hat KEINE Spalte `invoice_type`/
`total_amount`/`business_entity_id`) existiert weiterhin in:

- app/services/banking/payment_automation_service.py (6x invoice_type)
- app/services/digital_twin_service.py (2x)
- app/services/finanzki/predictive_cashflow_service.py (4x)
- app/services/holding/holding_kpi_service.py (10x, inkl. group_by auf invoice_type!)
- app/services/insights/skonto_optimizer.py (2x — ACHTUNG: Kommentare
  vertauscht: `incoming  # Forderung` / `outgoing  # Verbindlichkeit`;
  bei der Umstellung Richtungssemantik pruefen)
- app/services/predictive/cashflow_predictor_service.py (2x)
- total_amount zusaetzlich in: analytics/industry_benchmark_service.py,
  ceo_dashboard/trend_analyzer.py, company_metrics_service.py,
  dashboard/customer_ltv_service.py, dashboard/supplier_performance_service.py,
  finanzki/fraud_detection_service.py, finanzki/risk_intelligence_service.py
- business_entity_id zusaetzlich in: banking/proactive_dunning_service.py:576,
  pipeline/document_pipeline_orchestrator.py:1010

Empfehlung: mechanischer Sweep mit dem vorhandenen Helper (Muster +
Tests siehe `tests/unit/services/ai/test_invoice_direction_drift.py`).

## Befund 3: 8 weitere Duplicate-Operation-IDs (ausserhalb Zone/Queue)

Via `app.openapi()` verifiziert (nach dashboard_builder-Fix verbleibend):
- banking/connections.py: approve_payment, cancel_payment (kollidiert mit banking/payments)
- cashflow.py: get_cashflow_summary
- supplier_ocr_templates.py: list_template_candidates
- entities verify_entity (slowapi-Wrapper)
- annotations_enhanced.py + annotations_extended.py: delete_annotation (2x), create_reply

## Befund 4: UBL-Feldextraktion nicht implementiert (Feature-Gap)

`EInvoiceParserService` nutzt ausschliesslich den CII-`ZUGFeRDMapper`;
`XRechnungUBLMapper` kann nur GENERIEREN. UBL-XRechnungen (eine der zwei
gesetzlichen Syntaxen) werden geparst ohne Feldextraktion
(invoice_number/buyer_reference/Betraege = None). Test dokumentiert den
Gap ehrlich via skip (test_parse_ubl_buyer_reference). Der frueher dabei
auftretende Parser-CRASH (version=None -> AttributeError) ist gefixt.

## Hinweis: verbleibende bekannte Failures in test_einvoice_integration

Keine — Datei steht auf 56 passed / 1 skipped (der dokumentierte UBL-Gap).

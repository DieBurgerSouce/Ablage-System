# RLS-Restrunde — Policy-Bestandsaufnahme (Vorbereitung Migration 273)

**Datum:** 2026-07-11 (Nacht) · **Quelle:** read-only `pg_policies`-Abfrage gegen die Live-Dev-DB (Rolle-unabhängig) · **Kontext:** Deep-Review §4 „Rest-Härtung" + Go-Live-Runbook R-9. Migration 272 hat die USING-Escapes NUR auf `documents` entfernt — dieser Audit kartiert, was analog offen ist. **Anwendung einer Folge-Migration ist GATE-pflichtig (Muster 272: vorbereitet → Ben führt `alembic upgrade head` aus → Live-Verifikation).**

## Befunde (pg_policies, 2026-07-11)

| Tabelle | Befund | Klasse |
|---|---|---|
| `invoices` | **F-15-Klasse-Escape noch vorhanden**: `invoices_company_isolation` UND `invoices_tenant_isolation` enthalten `company_id IS NULL` in USING **und** WITH CHECK → NULL-Company-Zeilen sind für jeden sichtbar/schreibbar | analog zu dem, was 272 bei documents entfernt hat |
| `approval_requests` | dito: `approval_requests_tenant_isolation` mit `company_id IS NULL`-Escape in USING+WITH CHECK | analog |
| `documents` | `documents_insert` mit `WITH CHECK (true)` (bekannt); zusätzlich erlauben `documents_company_isolation` (ALL) und `documents_tenant_isolation` (WITH CHECK inkl. `company_id IS NULL`) INSERTs — **permissive OR: Verschärfen von `documents_insert` allein ändert NICHTS**, alle INSERT-fähigen Policies müssen zusammen betrachtet werden | Kern-Feinarbeit der 273 |
| `companies` | Einzige Policy `company_access_policy` hat **keine `is_rls_bypass_enabled()`-Klausel** → Worker-Bypass wirkt hier NICHT (live bestätigt 11.07.: Worker-Session sieht 0 companies). Für die heutige Pipeline unkritisch (odoo_tasks liest erp_connections, nicht companies), aber jeder künftige Worker-Codepfad, der companies liest, fällt still auf 0 Zeilen | Konsistenz-Lücke |
| `document_versions` | Nur superuser(`app.is_admin`)- und tenant-Policy, **keine Bypass-Klausel** → Worker ohne Company-Kontext liest 0 Versionen | Konsistenz-Lücke |

## Vorgeschlagener 273-Scope (für frische Session)

1. `invoices` + `approval_requests`: `company_id IS NULL`-Escapes aus USING entfernen (WITH CHECK zunächst unberührt — exakt das 272-Muster inkl. downgrade), VORHER zählen, wie viele NULL-company-Zeilen existieren (die würden unsichtbar → ggf. Backfill nötig wie bei Mig 268 business_entities).
2. `documents`-INSERT-Mandantentrennung: alle drei INSERT-wirksamen Policies gemeinsam neu schneiden (bypass ∨ company-match; `documents_insert (true)` fällt weg) — Regressionstest: Worker-Mirror-INSERT (Bypass) + API-Upload (Company-Kontext) + kontextloser INSERT (abgelehnt).
3. `companies` + `document_versions`: `is_rls_bypass_enabled()`-Klausel ergänzen (Konsistenz mit den übrigen Kern-Tabellen) — sonst bricht der nächste Worker-Codepfad, der sie liest, still.
4. Verifikation wie DoD-8: je Tabelle Read/Write ohne Kontext = 0/abgelehnt, mit Company-Kontext = nur eigene, mit Bypass = alle; `test_rls_worker_context.py` erweitern.

**Warum jetzt NICHT umgesetzt:** permissive-Policy-Interplay ist Feinarbeit mit Fehlbuchungs-/Pipeline-Bruch-Potenzial; Anwendung ist Ben-gated; Ende einer langen Session ist der falsche Zeitpunkt für DB-Policy-Chirurgie. Dieser Audit ist die vollständige Vorarbeit.

# Invoice Model-DB-Drift Report

**Datum**: 2026-05-19
**Branch**: `sprint-0-pilot-hardening`
**Scope**: `app/db/models_invoice.py` ↔ `invoices` Tabelle ↔ Service-Layer
**Severity**: P1 — Runtime-Fail-Potenzial im BI-Service, Multi-Tenant-Defense-in-Depth fehlt

## Befund

Drei-Wege-Drift zwischen DB-Schema, SQLAlchemy-Model und Service-Layer:

### IST: DB-Schema `invoices` (laut Migration-Historie)

Migration 022 (initial), bestaetigt durch Migration 057 (FK-Constraint) und Migration 261 (Index auf `status`):

| Spalte | Typ | Constraint | Quelle |
|--------|-----|------------|--------|
| `id` | UUID | PK | 022 |
| `document_id` | UUID | FK documents, unique, NOT NULL | 022 |
| `company_id` | UUID | FK companies (via 057), nullable | 022, 057 |
| `invoice_number` | String(100) | unique, NOT NULL | 022 |
| `invoice_date` | Date | NOT NULL | 022 |
| `due_date` | Date | NOT NULL | 022 |
| `subtotal` | Numeric(12,2) | NOT NULL | 022 |
| `tax_amount` | Numeric(12,2) | default 0 | 022 |
| `total_amount` | Numeric(12,2) | NOT NULL | 022 |
| `currency` | String(3) | default 'EUR', NOT NULL | 022 |
| `status` | String(20) | default 'pending', NOT NULL, indexed (261) | 022, 261 |
| `payment_date` | Date | nullable | 022 |
| `notes` | Text | nullable | 022 |
| `created_at` | DateTime(tz) | server_default now() | 022 |
| `updated_at` | DateTime(tz) | nullable | 022 |

Indexes:
- `ix_invoices_invoice_number` (022)
- `ix_invoices_status` (022)
- `ix_invoices_due_date` (022)
- `ix_invoices_company_date` (company_id, invoice_date) (022)
- `ix_invoices_unpaid` (due_date, total_amount) WHERE status NOT IN ('paid','cancelled') (261)

Constraints:
- `fk_invoices_company_id` (companies.id) — hinzugefuegt in 057
- RLS Policies — aktiviert in 110, 210, 211 (Multi-Tenant via `company_id`)

**KEINE Migration hat `business_contact_id` oder `entity_id` zu `invoices` hinzugefuegt.**

### SOLL laut Model: `app/db/models_invoice.py`

| Spalte | Status |
|--------|--------|
| `id` | ✅ deklariert |
| `document_id` | ✅ deklariert |
| `company_id` | ❌ **FEHLT** — existiert in DB, nicht im Model |
| `business_contact_id` | ⚠️ **PHANTOM** — im Model, NICHT in DB |
| `invoice_number` | ✅ deklariert |
| `invoice_date` | ✅ deklariert |
| `due_date` | ✅ deklariert |
| `subtotal`, `tax_amount`, `total_amount` | ✅ deklariert |
| `currency` | ✅ deklariert |
| `status` | ✅ deklariert |
| `payment_date` | ✅ deklariert |
| `notes` | ✅ deklariert |
| `created_at`, `updated_at` | ✅ deklariert |

Beziehungen im Model:
- `document = relationship("Document", backref="invoice")` — OK
- `business_contact = relationship("BusinessContact", backref="invoices")` — ⚠️ **PHANTOM** (FK existiert nicht)

### Service-Layer Verwendung

`app/services/business_intelligence_service.py`:
- Zeile 362, 547, 788: `Invoice.company_id == company_id` — **wuerde failen** (Model deklariert nicht, DB hat aber)
  - Actually: SQLAlchemy compiliert Spalten anhand des Class-Models. Da `company_id` NICHT im Model deklariert ist, wirft SQLAlchemy `AttributeError: 'Invoice' has no attribute 'company_id'` beim Query-Build.
- Zeile 368, 422: `Invoice.entity_id == ...` — **wuerde failen** (NIRGENDWO definiert: weder Model noch DB)

→ Diese BI-Code-Pfade sind **toter Code** oder **Runtime-Bombe**.

## Delta-Tabelle (Drift)

| Spalte | DB | Model | BI-Service | Risiko |
|--------|-----|-------|------------|--------|
| `company_id` | YES | NO | uses | **P1** — Multi-Tenant Defense-in-Depth fehlt, BI-Query failt |
| `business_contact_id` | NO | YES | not used | **P3** — Phantom-Column, INSERT/SELECT-Pfade waeren broken; aktuell nicht erreichbar |
| `entity_id` | NO | NO | uses | **P2** — BI-Service hat Runtime-Bombe / toten Code |

## Fix-Scope (dieses Patches)

**Narrow scope per Goal-Definition (Task B)**:
1. ✅ `company_id` Column zu Model hinzufuegen (UUID, FK companies.id, nullable=True, index=True)
2. ✅ Index `ix_invoices_company_id` zu `__table_args__` ergaenzen (DB hat bereits `ix_invoices_company_date` aus Migration 022, der erste Spalte ist company_id — abdecked Standard-Lookups)
3. ❌ `entity_id` NICHT hinzufuegen (DB hat sie nicht)

**Follow-up Status (Update 2026-05-19 spaeter Tag)**:

- **F1** ✅ **DONE** (Commit nach Task D): `business_contact_id` Column + relationship +
  `ix_invoices_contact_date` Index aus `app/db/models_invoice.py` entfernt.
  Verifikation: 0 Code-Stellen ausserhalb des Models nutzten das Feld, keine Migration
  hatte die DB-Spalte je angelegt. Tests gruen (14 passed).
- **F2** ✅ **DONE** (Commit nach F1): BI-Service `Invoice.entity_id` + `Document.entity_id`
  Runtime-Bomben aufgeloest. Untersuchung ergab 7 Treffer (Invoice.entity_id 5x,
  Document.entity_id 2x) in `analyze_invoices`, `search_documents`,
  `get_entity_statistics`, `predict_payment`. Code-Path lebt (von `app/api/v1/rag.py`
  aufgerufen, 8 Stellen), Option B (JOIN) gewaehlt.
  - Gewaehlte Loesung: JOIN Document via `Invoice.document_id == Document.id`,
    entity-Bezug ueber `Document.business_entity_id` (Invoice hat kein entity_id,
    InvoiceTracking-Model exposiert das DB-Feld auch nicht).
  - `Document.entity_id`-Stellen: simple Rename auf `business_entity_id` (Document
    hat nie `entity_id`, nur `business_entity_id`).
  - Folge-Drift: InvoiceTracking Model hat `entity_id` auch nicht deklariert obwohl
    DB-Spalte via Migration 094 existiert (separater Cleanup-Kandidat F4).
- **F3** ✅ **DONE** (Commit `e1e99825`): Invoice-API von `Document.owner_id`
  auf `Document.company_id` umgestellt (19 Endpoints, FastAPI-Dependency-Pattern).
- **F4** ✅ **DONE** (2026-05-20, Sprint-1 S1.5): `InvoiceTracking.entity_id`
  Column nachgezogen in `app/db/models_entity_business.py:534`. DB-Spalte
  existierte seit Migration 094 (FK business_entities, ondelete SET NULL,
  nullable, indexed). 50+ Service-Stellen nutzten `InvoiceTracking.entity_id`
  ohne dass das Model die Spalte deklarierte — Drift-Pattern analog zu Task B
  (`Invoice.company_id`). Fix: Column + relationship `entity` + Index
  `ix_invoice_tracking_entity_id` in `__table_args__` ergaenzt. Migration: KEINE
  noetig — DB-Spalte besteht bereits. Tests: bestehende Tests die
  `InvoiceTracking.entity_id` nutzen (z.B. Fraud-Detection, Cashflow-Predictor)
  laufen jetzt mit deklarierter Column.

## Verifikation

Nach Patch ausgefuehrt:
- `Invoice.__table__.columns` zeigt `company_id` ✅
- ruff/mypy auf `app/db/models_invoice.py` sauber
- BI-Service-Smoke-Test optional (Bug F2 bleibt bestehen)

Migration: **KEINE noetig** — DB-Spalte existiert seit Migration 022.

## Rollback

`git revert <commit-sha>` — komplett reversibel, da nur Python-Code-Change.

## Anhang: Migrationen die invoices beruehren

```
022_add_invoices_table.py         (initial schema)
057_add_multi_company_support.py  (FK fk_invoices_company_id)
110_comprehensive_rls_policies.py (RLS Multi-Tenant)
148_add_einvoice_transmission.py  (peppol_participants/incoming_einvoices, NICHT invoices)
210_add_rls_policies.py           (RLS V1)
211_rls_coverage_audit.py         (RLS Audit)
236_company_cascade_to_restrict.py (FK cascade -> restrict)
261_add_query_performance_indexes.py (ix_invoices_unpaid)
```

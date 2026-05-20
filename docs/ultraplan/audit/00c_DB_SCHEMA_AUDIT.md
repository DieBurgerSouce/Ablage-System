# 00c — DB Schema Audit (Pilot Reality Check)

**Scope**: `app/db/` (95 model-bezogene `.py`-Dateien, 43.585 LOC) + `alembic/versions/` (227 Migrationen).
**Stichtag**: 2026-05-03, Branch `feature/ocr-performance`.
**Ziel**: Pilot-Readiness der relationalen Schicht bewerten (GoBD, Multi-Tenancy, Event-Sourcing, RAG, pgvector).

---

## 1. Model-Inventar (Top-15 nach LOC)

Hinweis: Das Verzeichnis `app/db/models/` (Plural-Subdir) existiert als leeres Stub-Directory; der gesamte Code liegt in `app/db/models*.py` (top-level). Insgesamt 95 Files mit ca. **468 Modellklassen** (gezaehlt via `class .*\(Base\)`).

| Datei | LOC | Klassen |
|---|---:|---:|
| `app/db/models_entity_business.py` | 2180 | 20 |
| `app/db/models.py` (core: User, Document, AuditLog, ...) | 1655 | n/a |
| `app/db/models_gdpr_compliance.py` | 1473 | 22 |
| `app/db/models_privat_enterprise.py` | 1262 | 19 |
| `app/db/models_misc.py` (DomainEvent, EventSnapshot) | 1235 | 19 |
| `app/db/models_ocr_validation.py` | 1071 | n/a |
| `app/db/models_contract.py` | 1019 | n/a |
| `app/db/models_hr.py` | 981 | n/a |
| `app/db/models_datev.py` | 941 | n/a |
| `app/db/models_privat_space.py` | 926 | 17 |
| `app/db/models_banking.py` | 879 | n/a |
| `app/db/models_auth_access.py` | 862 | n/a |
| `app/db/models_cash_company.py` | 856 | n/a |
| `app/db/models_erp_import.py` | 827 | n/a |
| `app/db/models_autonomy.py` | 773 | n/a |

**Gesamt LOC**: 43.585 — `models.py` ist mit 1655 Zeilen der monolithische Kern (User, Document, AuditLog, SystemMetrics).
**`app/db/mixins/`**: nur `__init__.py` + `optimistic_lock.py` (Pflege duenn).
**`app/db/models_base.py`**: Definiert `Base`, `CrossDBJSON`, `CrossDBTSVector`, `CrossDBVector`, `SoftDeleteMixin` (Zeile 52-64).

---

## 2. Foreign-Key-Konzentration (Top-10)

`grep -c "ForeignKey"`:

| Rank | Datei | FK-Count |
|---:|---|---:|
| 1 | `app/db/models_entity_business.py` | **57** |
| 2 | `app/db/models_hr.py` | 50 |
| 3 | `app/db/models_banking.py` | 48 |
| 4 | `app/db/models_privat_space.py` | 44 |
| 5 | `app/db/models_misc.py` | 41 |
| 6 | `app/db/models_gdpr_compliance.py` | 40 |
| 7 | `app/db/models_cash_company.py` | 38 |
| 8 | `app/db/models_privat_enterprise.py` | 34 |
| 9 | `app/db/models_contract.py` | 30 |
| 10 | `app/db/models.py` | 30 |

`models_entity_business.py` ist das relationale Zentralgestirn (BusinessEntity, Customer, Supplier, Address, Contact). Refactoring-Kandidat fuer Bounded-Context-Trennung.

---

## 3. Multi-Tenancy-Audit (KRITISCHE LUECKE)

**Befund**: Das System nutzt **`company_id` als Tenant-Diskriminator**, nicht `tenant_id`.

- `tenant_id`: nur **2 Files** (`models_privat_space.py:428` mit FK auf `privat_tenants.id`, `schemas.py`). Das ist eine private/persoenliche Tenant-Ebene, NICHT die Firma.
- `company_id`: **616 Vorkommen in 82 Files** (gegen 95 gesamt).

**Files OHNE jegliche Tenant-Spalte (`company_id` UND `tenant_id`)**:

| Datei | Risiko | Begruendung |
|---|---|---|
| `app/db/models_invoice.py` | **HOCH** | `Invoice` (Z.38) hat nur `document_id`, `business_contact_id` — keine direkte Company-Isolation. Tenant-Isolation nur transitiv ueber Document. |
| `app/db/models_chat_actions.py` | MITTEL | `ChatToolAction` ohne Tenant-Spalte (Z.30). |
| `app/db/models_collaboration.py` | MITTEL | `DocumentMention` (Z.23) — nur via Document. |
| `app/db/models_dashboard_share.py` | MITTEL | `DashboardShare` (Z.35) — Sharing-Tabelle, ggf. Cross-Company-Leak. |
| `app/db/models_partitioning.py` | NIEDRIG | `PartitionManagement` (Z.64) — System-/Infra-Tabelle, akzeptabel. |
| `app/db/models_annotations_extended.py` | MITTEL | Reine Annotations-Erweiterung. |
| `app/db/models_auth_access.py` | NIEDRIG | RBAC-Tabellen sind zentral by design. |
| `app/db/models_encryption.py` | NIEDRIG | Key-Mgmt zentral. |
| `app/db/models_notification_template.py` | NIEDRIG | Template-Bibliothek (system-weit). |
| `app/db/models_privat_contracts.py` | MITTEL | Nutzt `tenant_id` (privat_tenants), kein `company_id`. |
| `app/db/models_surya_training.py` | NIEDRIG | ML-Training data. |
| `app/db/models_webhook_inbound.py` | MITTEL | Inbound webhooks ohne Mandantenfilter. |

**Migrationen 257-261**: KEINE davon ist Multi-Tenant-Backfill. 257 = CHECK Constraints, 258 = Indizes, 259 = RBAC-Seed, 260 = Domain-CHECKs (Confidence/Amount), 261 = Performance-Indexe. Multi-Tenant-Backfills lagen frueher (071, 098, 134, 251).

---

## 4. Soft-Delete-Audit

`grep -c "deleted_at|SoftDeleteMixin"`: **88 Vorkommen in 22 Files** (von 95 = ~23 % der Module).

- `SoftDeleteMixin` definiert in `app/db/models_base.py:52`.
- Top-Nutzer: `models_privat_space.py` (12), `models_entity_business.py` (8), `models_hr.py` (7), `models_cash_company.py` (6), `models.py` (5).
- Migration `streckengeschaeft_002_soft_delete.py` + `_003_extend_soft_delete.py` retro-fitted ein Subset.

**Luecke**: `Invoice`, `ChatToolAction`, `DocumentMention`, `DomainEvent` (event-sourced — by design append-only, korrekt), `AuditLog` (auch korrekt unveraenderbar). Kein einheitliches Pattern; manuelle Filterung in Queries notwendig (siehe Mixin-Doc).

---

## 5. CashEntry GoBD-Constraints

Datei: `app/db/models_cash_company.py:342` (`class CashEntry(Base)`).

| Constraint | Zeile | Status |
|---|---:|---|
| `amount != 0` | 463 | OK (`ck_cash_entries_amount_not_zero`) |
| `entry_date <= CURRENT_DATE` (no future) | 465 | OK (`ck_cash_entries_no_future_date`) |
| Unique `(cash_register_id, fiscal_year, entry_number)` | 454 | OK |
| ondelete="RESTRICT" auf `companies.id`, `cash_registers.id`, `created_by_id` | 361, 366, 442 | OK (verhindert Mandanten-Loeschung mit Bewegungen) |

Storno-Pattern korrekt umgesetzt: `is_cancelled`, `cancelled_by_entry_id` (Self-FK), `cancelled_by_user_id`, `cancelled_at`. Append-only-Vertrag im Docstring (Z.343-353).

---

## 6. AuditLog Hash-Chain

Datei: `app/db/models.py:842` (`class AuditLog(Base)`).

| Feld | Zeile |
|---|---:|
| `sequence_number` (BigInteger, unique, indexed) | 889 |
| `previous_hash` (String 64) | 893 |
| `integrity_hash` (String 64, eigentlich "current") | 891 |
| `company_id` (Multi-Tenant-Isolation, Migration 134) | 861 |

Indexe: `ix_audit_logs_sequence`, `ix_audit_logs_company_created`. Docstring (Z.851-853) verweist auf DB-Trigger gegen UPDATE/DELETE (Migration 017). Gut.

**Anmerkung**: Field heisst `integrity_hash`, nicht `current_hash` — konsistent benutzbar, aber in Standard-Hash-Chain-Literatur ungewoehnlich. Nicht-blockierend.

---

## 7. DomainEvent (Event Sourcing, Apr 2026)

Datei: `app/db/models_misc.py:814` (`class DomainEvent(Base)`).

Volle Hash-Chain implementiert:
- `event_hash` (Z.845)
- `previous_hash` (Z.846)
- `chain_hash` (Z.847, indexed)
- `sequence_number`, `correlation_id`, `causation_id` (Z.829, 837, 838)
- Multi-Tenant: `company_id` mit ondelete CASCADE (Z.819)
- `UniqueConstraint(aggregate_type, aggregate_id, sequence_number)` (Z.853)
- Ergaenzendes `EventSnapshot` (Z.863) fuer Performance.

Migration: `254_event_store_hash_chain.py` (2026-02-23). Sehr ordentlich.

---

## 8. Letzte 10 Migrationen

| ID | Datei | Beschreibung |
|---:|---|---|
| 252 | `audit_fields_payment_batch_dunning_record.py` | `created_by_id` / `updated_by_id` fuer GoBD |
| 253 | `gobd_gdpr_compliance_views.py` | SQL-Views: `gobd_audit_summary`, `gdpr_deletion_status` |
| 254 | `event_store_hash_chain.py` | SHA-256 Hash-Chain fuer `domain_events` |
| 255 | `entity_seasonal_patterns.py` | Persistenz Saisonal-Pattern |
| 256 | `fk_cascade_audit.py` | ondelete CASCADE/SET NULL Audit |
| 257 | `add_missing_constraints.py` | CHECKs: chain_position, BatchJob progress 0-100, Priority 1-10 |
| 258 | `add_missing_indexes.py` | Partial-Indexe (soft-deleted), GIN auf JSONB |
| 259 | `seed_default_roles.py` | RBAC Default-Rollen (admin, manager, user, viewer, tax_advisor) |
| 260 | `add_domain_constraints.py` | Confidence 0-1, Amount >= 0 |
| 261 | `add_query_performance_indexes.py` | Composite + FK-Indexe (company+date, user+action) |

**Multi-Tenant-Backfills 257-261?** Nein — keine. Echter Multi-Tenant-Backfill liegt in **`134_*` (audit_logs.company_id)**, **`071_add_company_id_to_documents.py`**, **`098_multi_tenant_enhancements.py`**, **`104_add_tenant_subscription_system.py`**, **`110_comprehensive_rls_policies.py`**, **`251_add_company_id_to_document_groups.py`**.

---

## 9. RAG-Tables

Migration `alembic/versions/033_add_rag_tables.py` legt an:
- `rag_document_chunks` (Embeddings)
- `rag_customer_cards` (pre-computed customer summaries)
- `rag_chat_sessions` (Chat history)
- `rag_chat_messages`
- `rag_llm_models`

Folge-Migrationen: `036_fix_embedding_dimensions.py`, `043_add_vector_ab_testing.py`, `044_nullable_chunk_embedding.py`, `052_add_chat_session_sharing.py`, `212_chat_tool_actions.py`. RLS-Coverage in `110_comprehensive_rls_policies.py`. Models in `app/db/models_rag.py` (518 LOC, 27 Indexe).

---

## 10. pgvector

Verwendung von `Vector(dim)` ueber `CrossDBVector` (`app/db/models_base.py:37-49`, dialect-aware: pgvector auf PG, Text auf SQLite):

| Datei:Zeile | Spalte | Dim |
|---|---|---:|
| `app/db/models.py:211` | `Document.embedding` | 1024 (multilingual-e5-large) |
| `app/db/models_clustering.py:71` | Cluster-Centroid | 1024 |
| `app/db/models_rag.py:128` | `RAGDocumentChunk.embedding` | 1024 |
| `app/db/models_rag.py:212` | `RAGCustomerCard.card_embedding` | 1024 |
| `app/db/models_rag.py:485` | Chat-Query-Cache | 1024 |

5 Vector-Spalten — konsistent 1024-dimensional. Saubere Cross-DB-Abstraktion.

---

## 11. Indexe

- `Index(...)` insgesamt: **1257 Vorkommen / 95 Files**.
- `"ix_..."` Naming: **1257** (identische Zahl — striktes Naming-Pattern eingehalten).
- Top-Index-Files: `models_entity_business.py` (76), `models_ocr_validation.py` (73), `models.py` (60), `models_privat_space.py` (48), `models_auth_access.py` (42), `models_datev.py` (41), `models_gdpr_compliance.py` (40).
- Migrationen 258 + 261 ergaenzen Performance- und FK-Indexe.

---

## Top-3 Staerken

1. **GoBD-Konformitaet hoch**: CashEntry mit CHECK-Constraints + Append-Only-Pattern (`models_cash_company.py:342-466`); AuditLog Hash-Chain mit `sequence_number/previous_hash/integrity_hash`; Event-Store mit voller Hash-Chain (`event_hash`, `previous_hash`, `chain_hash`) plus EventSnapshot. Migrations 252, 253, 254 untermauern Compliance-Reife.
2. **Cross-DB-Typ-Layer**: `models_base.py` mit `CrossDBJSON`, `CrossDBTSVector`, `CrossDBVector` ermoeglicht SQLite-Tests + PostgreSQL-Production ohne Code-Branches — selten so sauber.
3. **Index-Disziplin**: 1257 Indexe mit konsistentem `ix_`-Praefix; partial + GIN-Indizes (Migration 258) und Composite-Indexe (261) auf High-Traffic-Pfaden.

## Top-5 Luecken

1. **Inkonsistente Tenant-Spalte**: System nutzt `company_id` als faktischen Tenant-Diskriminator (82/95 Files), aber die UltraPlan-Sprache impliziert `tenant_id`. Dokumentation widerspricht Code. Empfehlung: Begriff in CLAUDE.md/Docs vereinheitlichen ODER Tenant-Wrapper einfuehren.
2. **Multi-Tenant-Loecher in Satellite-Models**: `Invoice` (`models_invoice.py:38`), `ChatToolAction`, `DocumentMention`, `DashboardShare` — keine direkte `company_id`-Spalte, Isolation nur transitiv ueber FK-Joins. Bei Cross-Tenant-JOIN-Bug oder fehlendem RLS-Filter -> Datenleck. **Pilot-Blocker** fuer `Invoice` (kerngeschaeftliche Tabelle).
3. **Soft-Delete-Coverage 23 %**: 22/95 Files nutzen `deleted_at` — kein einheitliches Lifecycle-Pattern. Mixin filtert auch nicht automatisch (siehe Doc Z.60). Risiko: Geloeschte Daten sichtbar in Reports.
4. **`models.py` Monolith**: 1655 LOC mit User, Document, AuditLog, SystemMetrics — verletzt Bounded-Context-Idee, die Satellite-Models (z.B. `models_invoice.py`) bereits umsetzen. Erschwert konfliktfreie Parallelarbeit.
5. **`tenant_id` Begriffs-Doppelnutzung**: `models_privat_space.py:428` referenziert `privat_tenants.id` als `tenant_id` (Privat-Modul), waehrend Business-Daten `company_id` nutzen. Zwei parallele Mandanten-Konzepte ohne klare Doku — Risiko fuer Cross-Modul-Joins.

---

## Pilot-Readiness-Note: **7 / 10**

**Plus**: GoBD/Audit/Event-Sourcing sehr reif; pgvector/RAG-Schema sauber; Migrations-Hygiene gut (227 numerisch, klare Beschreibungen, Backfills + Constraints + Indexe getrennt). Hash-Chains, CHECK-Constraints, Index-Coverage produktionsnah.

**Minus**: Multi-Tenant-Begriffsverwirrung (`company_id` vs `tenant_id`) ist konzeptionell unsauber und konkret blocking fuer `Invoice` (kein `company_id`). Soft-Delete uneinheitlich. `models.py`-Monolith blockiert parallele Feature-Arbeit.

**Vor Pilot zwingend**: (a) `company_id` zu `invoices` + zugehoerige Backfill-Migration; (b) RLS-Coverage fuer alle 13 tenant-losen Files dokumentieren oder schliessen; (c) Glossar-Entscheidung `tenant_id` vs `company_id` und Wording-Harmonisierung.

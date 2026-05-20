# 00b BACKEND AUDIT — Pilot-Reality-Check

Stand: 2026-05-03. 797 `.py`-Files unter `app/services/`. Brutal-Mode.

---

## 1. TOP-15 Subdirectories nach File-Count

#BucketFiles1-Satz-Beschreibung1`app/services/ai/`52Sammelbecken fuer LLM-, Fraud-, Smart-Dunning-, Cashflow-Predictions — Kuechen-Spuele-Modul.2`app/services/banking/`45Skonto, Teilzahlungen, Reconciliation, FinTS — Kern-Geschaeft-Domaene.3`app/services/privat/`38Privatvermoegen-Modul (Property, Tax-Optimization, Life-Events) — separater Bounded Context.4`app/services/compliance/`23GoBD, GDPR, Audit-Chain, Retention.5`app/services/datev/`22DATEV Connect + Kontenrahmen-Mapping.6`app/services/orchestration/`20Cross-Module-Orchestrator + Seasonal-Detector.7`app/services/rag/`16Retrieval-Augmented Generation Stack (Embeddings, Chunking).8`app/services/extraction/`15Strukturierte Feld-Extraktion aus OCR-Output.9`app/services/einvoice/`15XRechnung / ZUGFeRD Parser + Schemas.10`app/services/ocr/`14OCR-Pipeline-Adapter (DeepSeek, GOT, Surya).11`app/services/bpmn/`14BPMN-Workflow-Engine.12`app/services/workflow/`13Approval-/Routing-Workflows (Overlap mit `bpmn/` und `approval/`).13`app/services/contracts/`12Vertragsverwaltung + Kuendigungs-Tracking.14`app/services/accounting/`11Buchungssaetze, SKR03/04.15`app/services/external/`10External-API-Wrapper (Lexware, Bundesbank, Carrier).

**Befund**: `ai/` als Top-Bucket ist ein Smell. 52 Files in einem Pseudo-Modul deutet auf fehlende Subdomain-Schnitte hin. `workflow/` + `bpmn/` + `approval/` sind drei ueberlappende Buckets — wahrscheinlich Duplikat-Verantwortung.

---

## 2. TOP-10 schwergewichtigste Files

#FileBytes1`app/services/structured_extraction_service.py`118.2682`app/services/privat/tax_optimization_service.py`98.9073`app/services/streckengeschaeft/__init__.py`87.5844`app/services/quick_classification_service.py`78.6385`app/services/backup_service.py`72.1416`app/services/ai/finance_assistant_service.py`70.9947`app/services/search_service.py`67.8988`app/services/backend_manager.py`65.7559`app/services/training_dataset_export_service.py`63.47510`app/services/ocr_pipeline.py`61.939

**Befund**: 87 KB im `__init__.py` von `streckengeschaeft/` ist ein klares Anti-Pattern (Logik im Package-Init statt in Modulen). Strukturen &gt;60 KB pro Datei sind God-Objects — nicht testbar, nicht reviewbar.

---

## 3. TOP-10 verdaechtig leere Files (&lt; 10 Zeilen Logik)

#FileLogik-Zeilen1`app/services/ai_ethics/__init__.py`12`app/services/calendar/__init__.py`13`app/services/ceo_dashboard/__init__.py`14`app/services/knowledge_graph/__init__.py`15`app/services/lexware/__init__.py`16`app/services/monitoring/__init__.py`17`app/services/privat/life_events/__init__.py`18`app/services/scanner/__init__.py`19`app/services/templates/__init__.py`110`app/services/webhooks/__init__.py`1

**Befund**: 10 `__init__.py` mit 1 Zeile heisst nicht zwingend "leer", aber `ai_ethics/`, `ceo_dashboard/`, `knowledge_graph/`, `scanner/`, `templates/`, `webhooks/` als komplette Top-Level-Packages mit nur 1-Zeilen-Init sind verdaechtig — entweder Stub-Module fuer Roadmap-Theater oder echte aber unausgebaute Skelette. Pilot-Risiko: tote Pfade in der Architektur-Doku.

---

## 4. Async-Hygiene-Spotcheck: `asyncio.run(`

Treffer in `app/services/`:

- `app/services/adhoc_report_service.py:991` — `pdf_bytes = asyncio.run(...)` **innerhalb einer Service-Methode**. Das ist ein Bug-Magnet: `asyncio.run` von einem bereits laufenden Loop crasht mit `RuntimeError: This event loop is already running`. Wird unter Celery oder FastAPI fast garantiert explodieren.
- `app/services/backup_report_service.py:580` — `asyncio.run(main())` in einem `if __name__ == "__main__"`-Block. Akzeptabel als Script-Entry, aber dann gehoert die Datei nicht in `services/`.

**Verdikt**: 1 echter Bug (`adhoc_report_service.py:991`), 1 Style-Issue.

---

## 5. N+1-Query-Spotcheck: 5 zufaellige Services

File`selectinload`/`joinedload` vorhanden?Beleg`app/services/spotlight_service.py`NEINkeine `options(...)`-Aufrufe; reine SQL-Queries ohne Eager Loading`app/services/business_intelligence_service.py`JA`app/services/business_intelligence_service.py:23` `from sqlalchemy.orm import selectinloadapp/services/optimistic_lock_service.py`NEINkeine Eager-Loading-Imports`app/services/backup_report_service.py`NEINkeine ORM-Joins, vermutlich nur Reporting`app/services/document_services/crud_service.py`JA`crud_service.py:65, :124, :173, :240` `.options(selectinload(Document.tags))`

Repo-weit: **269** `.py`**-Files** unter `app/services/` nutzen `joinedload`/`selectinload` (\~33 % aller Service-Files). Heisst: Etwa zwei Drittel der Services haben kein dokumentiertes Eager-Loading-Pattern. Kein Beweis fuer N+1, aber starkes Indiz, insbesondere bei `spotlight_service` (Latenz-Ziel &lt;200 ms laut Header-Kommentar).

---

## 6. `except Exception: pass` Pattern

**56 Vorkommen** in `app/services/`. Hotspots:

- `app/services/access_analytics_service.py:840, :861` — Audit-Service schluckt Exceptions stumm. Compliance-Risiko.
- `app/services/imports/email_import_service.py:798, :822, :1111` — drei verschluckte Exceptions im Import-Pfad. Importe schlagen fehl, Nutzer sieht nichts.
- `app/services/imports/folder_import_service.py:839, :881, :1078` — gleiches Muster.
- `app/services/search_service.py:662, :672` — Such-Index-Aktualisierung kann silent fehlschlagen.
- `app/services/ai/fraud_detection_service.py:683` — Fraud-Detection schluckt eine Exception. Sicherheits-Smell.
- `app/services/orchestration/seasonal_detector_service.py:537` — Orchestrator schluckt.
- `app/services/auto_matching_service.py:314`, `app/services/diff/image_diff_service.py:193`, `app/services/imports/eml_file_parser.py:277`, `app/services/role_dashboard_service.py:197`, `app/services/smart_dashboard_service.py:881`.

**Verdikt**: Nicht katastrophal verteilt, aber praezise an den falschen Stellen — Compliance, Imports, Fraud. Ein Pilot wird Datenverluste nicht bemerken, weil sie weggeloggt werden.

---

## 7. Pydantic-Mix

- `from pydantic.v1 ...` Imports: **0 Treffer** in `app/`. Sauber.
- `BaseSettings` Verwendung: nur `app/core/config.py:24` und `:45` — Import aus `pydantic_settings` (Pydantic v2 Standard). Sauber.

**Verdikt**: Pydantic v2 durchgaengig. Keine Migration-Schulden hier.

---

## 8. Domain-Event-Service

- `app/services/events/` existiert: **JA**. Inhalt: `event_bus.py`, `__init__.py`. Implementiert Redis-PubSub-Event-Bus (laut Modul-Docstring: `document.ocr_completed`, `property.rental_received`, `vehicle.fuel_logged`, `deadline.approaching`, etc.). Nicht persistent, nur Pub/Sub-Coordination.
- `app/services/domain_events.py` als Top-Level-File: **NEIN** existiert nicht.
- Echtes Event-Sourcing dagegen unter `app/services/event_sourcing/`: `event_store.py` (610 Zeilen), `event_emitter.py` (75 Zeilen), `projection_service.py`, `snapshot_service.py`. **Das** ist die Domain-Event-Implementation.

**Verdikt**: Saubere Trennung — `events/event_bus.py` fuer Real-Time-PubSub, `event_sourcing/event_store.py` fuer persistente, auditierbare Events. Architektur-OK.

---

## 9. EventStore Hash-Chain (Commit `0559fd15`)

Implementiert in `app/services/event_sourcing/event_store.py`:

- `event_store.py:44` — `GENESIS_PREVIOUS_HASH = "0" * 64`
- `event_store.py:167` — `event_hash = self._calculate_event_hash(...)`
- `event_store.py:174` — `previous_chain_hash = await self._get_previous_chain_hash(...)`
- `event_store.py:180` — `chain_hash = self._calculate_chain_hash(previous_chain_hash, event_hash)`
- `event_store.py:482` — `_calculate_event_hash` (kanonisches JSON, sort_keys=True, SHA-256)
- `event_store.py:507` — `_calculate_chain_hash` (SHA-256 ueber `previous_hash + event_hash`)
- `event_store.py:515` — `_get_previous_chain_hash`
- `event_store.py:540` — `verify_chain` (rekonstruiert + vergleicht Kette)

**Verdikt**: Solide implementiert, kanonisches JSON mit `sort_keys=True` und `separators=(",", ":")` — Hash-Determinismus gegeben. Inklusive Verify-Pfad. **Echter Audit-Anker**, kein Theater.

---

## 10. Multi-Tenant-Status

- `tenant_id` in `app/services/`: **42 Treffer** (`grep -c`).
- `tenant_id` in `app/db/`: **5 Treffer** (`grep -c`, ohne pycache).

Beleg-Quellen:

- `app/db/models_privat_space.py:428` — `tenant_id = Column(... ForeignKey("privat_tenants.id"))` — bezieht sich auf **Mieter** (Privat-Modul, Vermietung), NICHT auf SaaS-Mandanten.
- `app/db/schemas.py:6109, :6125, :6150, :6168` — Pydantic-Schemas fuer Mieter-Daten.
- `app/services/auth/sso/sso_config_service.py:113-201` — `tenant_id` ist Microsoft-Azure-AD-Tenant-Parameter (OAuth Endpoint-Path), kein App-Mandant.
- `app/services/permission_service.py:129` — `tenant_id = company_id if company_id else "global"` — Permission-Cache-Key. Wird `company_id` als Mandanten-Proxy verwendet, aber kein durchgaengiges Mandanten-Modell.
- `app/services/document_grouping_service.py:851, :871` — gleiches Muster, `tenant_id = company_id or owner_id`.

**Verdikt**: **Es gibt keine echte Multi-Tenancy.** Die 42 Treffer im Service-Layer sind ueberwiegend (a) Microsoft-AD-Tenant-IDs fuer SSO, (b) Mieter-IDs aus dem Privatraum-Modul, (c) ad-hoc `company_id`-Aliasing in Permission-/Grouping-Caches. Auf DB-Ebene **eine einzige Tabelle** mit `tenant_id`-Spalte — die `models_privat_space`-Mieter-Tabelle. Kein Row-Level-Security, keine Schema-Trennung, kein Multi-Tenant-Index. Pilot mit mehreren Kunden auf einer Instanz: nicht moeglich ohne Re-Architektur. Bei Single-Customer-Deployment (on-premises pro Kunde) ist das tolerierbar — entspricht der CLAUDE.md-Aussage "On-premises, no cloud dependencies".

---

## TOP-3 STAERKEN

1. **EventStore-Hash-Chain ist Production-Grade** (`event_store.py:482-540`). Kanonisches JSON, SHA-256-Verkettung, Verify-Pfad, Genesis-Hash. Kombiniert mit `compliance/` + `event_sourcing/projection_service.py` ein echtes GoBD-Fundament.
2. **Pydantic v2 sauber durchgezogen.** Kein `pydantic.v1`-Import irgendwo, `BaseSettings` korrekt aus `pydantic_settings`. Keine versteckte Migration-Schuld.
3. **Architektur-Trennung Events vs. Event-Sourcing** ist erkennbar bewusst (`events/event_bus.py` Redis-PubSub, `event_sourcing/event_store.py` persistent + Hash-Chain). Senior-Level-Entscheidung, nicht zufaellig.

---

## TOP-5 LUECKEN

1. **Keine Multi-Tenancy.** 1 DB-Spalte `tenant_id`, und die meint Mieter, nicht Mandanten. Wer mehr als einen Pilotkunden auf einer Instanz hosten will, baut Monate. Pilot-Blocker fuer SaaS-Modell.
2. **God-Objects.** `structured_extraction_service.py` (118 KB), `tax_optimization_service.py` (99 KB), `streckengeschaeft/__init__.py` (88 KB Logik im Init-File!). Nicht testbar, nicht reviewbar. Bug-Fix-Latenz wird inakzeptabel.
3. **`asyncio.run(...)` in Service-Code** (`adhoc_report_service.py:991`). Garantierter Crash unter FastAPI/Celery wenn Code-Pfad getriggert wird. Lauert auf den ersten echten Report-Auftrag.
4. **56 `except Exception: pass`-Vorkommen** an genau den falschen Stellen: Audit (`access_analytics_service.py:840, :861`), Imports (`email_import_service.py`, `folder_import_service.py` je 3x), Fraud (`fraud_detection_service.py:683`). Pilot bekommt Datenverlust ohne Fehlermeldung.
5. **Eager-Loading inkonsistent.** Nur ~34 % der Service-Files importieren `joinedload`/`selectinload`. Latenz-kritischer `spotlight_service.py` (Ziel: <200 ms) hat keinerlei Eager-Loading. N+1-Verdacht akut.

---

## NOTE: BACKEND PILOT-READINESS — **6 / 10**

**Begruendung**:

- Plus: Hash-Chain, Pydantic-v2-Sauberkeit, Event-Sourcing-Architektur, 269 Files mit Eager-Loading, dokumentierte Domain-Trennung.
- Minus: Keine Multi-Tenancy, vier 60–120 KB God-Objects, 56 verschluckte Exceptions, mindestens ein konkreter `asyncio.run`-Bug, 10 vermutlich tote Top-Level-Packages, ueberlappende Workflow-Buckets (`workflow/`, `bpmn/`, `approval/`).

Pilot-fuer-einen-Kunden on-premises: **machbar**. Pilot-fuer-mehrere-Kunden / Multi-Tenant-SaaS: **nicht machbar** ohne 2–4 Monate Hardening. Code-Qualitaet ist mid-senior, aber die God-Objects + Silent-Catches reichen aus, um in Production unbemerkt Daten zu verlieren.

**Empfehlung vor Pilot-Go-Live**:

1. Fix `asyncio.run` in `adhoc_report_service.py:991`.
2. Audit aller 56 `except Exception: pass` — ersetzen durch `logger.exception(...)` mit reraise oder gezieltem Catch.
3. Spotlight-Service auf N+1 testen (Lasttest mit 1.000 Dokumenten).
4. Entscheidung: Single-Tenant-pro-Instanz ODER Multi-Tenant-Refactor planen.
5. `streckengeschaeft/__init__.py` (88 KB) zerlegen — Init-Files sind kein Code-Container.

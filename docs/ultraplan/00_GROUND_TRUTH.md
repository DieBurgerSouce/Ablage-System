# 00 — Ground Truth: Was existiert wirklich

**Datum:** 2026-05-03
**Branch:** `feature/ocr-performance` (5 commits ahead of master)
**Methode:** Code-Inventur + Git-Recency + Diff zu existierenden ANALYSIS-Reports

---

## TL;DR (Executive Summary)

Drei nicht-übereinstimmende Realitäten existieren parallel im Repository:

1. **ANALYSIS_*.md (Stand 2025-12-31):** 92-95% Production-Ready, 4.6/5 Enterprise.
2. **FAANG-Audit2.md (Stand 2025-12-31):** 7.5/10 - "Advanced Prototype". NEIN zu Release. Backend exzellent, Frontend hat UX-Lücken.
3. **Aktueller Code (Stand 2026-05-03):** Codebase hat sich seit Dez 2025 **knapp vervierfacht**. 797 Services (vs. 210), 299 Frontend-Routes (vs. 93), 227 Migrationen (vs. 70). Massive Skalierung der Code-Menge — ob auch der Reife-Grad mitgewachsen ist, bleibt zu prüfen (Phase 1 Audit).

**Zentrale Beobachtung:** Die ANALYSIS-Reports beschreiben einen Snapshot, der **nicht mehr existiert**. Das System ist substantiell weiter als die Reports beschreiben — und die Reports waren bereits damals von FAANG-Audit2 als "zu optimistisch" markiert. Wir müssen für die Pilot-Entscheidung den **aktuellen Code** bewerten, nicht die Reports.

---

## 1. Was existiert wirklich (Code-bewiesen)

### 1.1 Massive Backend-Codebase

| Metrik | ANALYSIS (Dez 2025) | Aktuell (Mai 2026) | Wachstum |
|--------|---------------------|---------------------|----------|
| Backend Services | 210 Files | **797 Files** | **+280%** |
| API Router Files | — | **298 Files** | (vorher 748+ Endpoints) |
| DB Model Files | — | **95 Files** (`models*.py`) | (vorher 132 Models in 1 File) |
| Alembic Migrationen | 70 | **227** | **+224%** |
| Frontend Routes | 93 | **299** | **+221%** |
| Frontend Features | — | **127 Module** | — |
| Tests Unit | — | **678** | — |
| Tests Integration | — | **53** | — |
| Tests E2E | — | **53 Files** | — |

(Quelle: `find app/services -name "*.py" \| wc -l` etc. ausgeführt 2026-05-03)

### 1.2 Verifizierte Kern-Features (ANALYSIS bestätigt + aktuell)

| Feature | Status laut ANALYSIS | Aktueller Code-Beleg |
|---------|----------------------|---------------------|
| Kassenbuch GoBD APPEND-ONLY | 5/5 | `app/services/banking/...` (15 Banking-Services), Migration mit CheckConstraint (siehe Hash-Chain in `EventStore SHA-256` Commit `0559fd15`) |
| Mahnwesen BGB §286/288 | 4/5 (1 Stub) | `app/services/banking/dunning_service.py` + `proactive_dunning_service.py`, B2B 11.27% / B2C 7.27% Verzugszinsen (laut `ANALYSIS_FEATURE_DEPTH.md:91-93`) |
| DATEV Export | 5/5 | `app/services/datev/connect/` + `export_service.py` (30 KB), SKR03/SKR04, Vendor-Mapping |
| Streckengeschäft | 5/5 | `app/services/drop_shipment/`, separate Migrations-Reihe (`streckengeschaeft_001-004`), 4-Stage-Detection-Cascade |
| Multi-Backend OCR | 5/5 | `app/services/ocr/`, `app/services/backend_manager.py`, Self-Learning-Service |
| RAG/Chat | 5/5 (laut ANALYSIS) | RAG-Pläne in `PlanRAGAblage.md` aber Status unklar (siehe §3) |
| Risk Scoring UI | "Vollständig implementiert" 2026-01-23 | `frontend/src/features/risk-scoring/` mit 6 Komponenten, RiskAlertBanner, RiskProfilePage, RiskDashboard |
| Spotlight Search | NEU (Mai 2026) | Commit `b81ed221` "feat(frontend): SpotlightDialog in AppLayout integriert + Spotlight Feature-Modul" |
| Domain Events + Hash-Chain | NEU (Apr-Mai 2026) | Commits `0559fd15`, `f4445fd5` — EventStore SHA-256 Hash-Chain + DomainEvent + EntitySeasonalPattern |
| Multi-Tenant Backfill | IN ARBEIT (Mai 2026) | Commit `cc9eadef` "Migrationen 257-261 + CheckConstraints + Banking Multi-Tenant Backfill Fix" |

### 1.3 Aktuelle Wellen (letzte 30 Commits)

Der Branch `feature/ocr-performance` zeigt, woran zuletzt gearbeitet wurde:

- **Migrations 257-261** mit CheckConstraints, Banking-Tenant-Backfill (`cc9eadef`, `78c3eb93`, `37ada754`)
- **Logging-Migration**: 89 Files von stdlib-logging zu structlog (`9385e8e4`, `0b33f604`) — strukturiertes Logging durchgängig
- **Type-Safety-Hardening**: `Dict[str, Any]` → `JSONDict` (`0519a60f`)
- **Soft-Delete-Hardening**: `SoftDeleteMixin + FK ondelete cascade audit (Phase 4 P2 Hardening)` (`b35597c7`)
- **GitHub Actions Digest-Pinning**, Docker Multi-Stage, Resource-Limits (`7128e72b`)
- **Nginx Security Headers**, Docker Hardening (`fd35c0a3`)
- **Tests**: 30+ neue Unit/Integration-Tests OCR/Banking/API/Security (`70092c55`)
- **Frontend Features (Mai 2026)**: SpotlightDialog, Dokumenten-Graph, Agent Chat, Annotation, Action Queue
- **Worker-Hardening**: Task error handling + startup health gate (`3b4b014b`)
- **Domain Events**: Documents, Entities, Invoices APIs (`2f6be8b7`)

**Beobachtung:** Es wurde im Q1-Q2 2026 systematisch gehärtet (Logging, Soft-Delete, FK-Cascade, Multi-Tenancy, CI-Pinning, Security-Headers). Das ist *Production-Hardening*, nicht *Feature-Building*.

---

## 2. Was existiert nur in Plänen (MD ohne Code-Backing)

### 2.1 RAG/LLM Intelligence Layer (`PlanRAGAblage.md`, 109 KB, Dez 2025)

Der größte Plan im Repository. Spezifiziert komplett:
- `rag_document_chunks` Tabelle mit pgvector(1024)
- `rag_customer_cards` mit pre-computed Summaries
- `rag_chat_sessions` + `rag_chat_messages`
- Qwen3-8B (Q5_K_M) auf RTX 4080
- multilingual-e5-large Embeddings
- bge-reranker-v2-m3 Reranker
- Customer-Cards-Service
- Report-Generator (Excel/PDF/Word)

**Code-Reality-Check (gegrepped 2026-05-03):**
- `pgvector` Extension wird genutzt (laut Memory `pgvector-Nutzung` confirmed bei AgentDB)
- `multilingual-e5-large` referenziert in `PlanVektorPipeline.md` als "bereits aktiv"
- Konkrete Tables `rag_document_chunks` / `rag_customer_cards` / `rag_chat_sessions`: **[UNGEKLÄRT: Migration-Audit nötig]**
- Qwen3-8B-Integration: **[UNGEKLÄRT: kein direkter Code-Hit, nur in Plänen]**
- Customer-Cards-Service: **[UNGEKLÄRT]**

→ Phase 1.10 (ML/Data-Audit) wird klären welche RAG-Bestandteile real sind.

### 2.2 Vektor-Pipeline mit Übersetzung (`PlanVektorPipeline.md`, Stand Dez 2025)

Plant:
- `app/services/translation_service.py` — MarianMT/NLLB für RU/EN/PL/UK/FR → DE
- `app/services/structured_extraction_service.py` — Qwen2.5-VL strukturierte JSON-Extraktion
- `app/agents/postprocessing/structured_extraction_agent.py`
- Neue DB-Felder: `extracted_text_original`, `source_language`, `extracted_data`

**Code-Reality-Check:** [UNGEKLÄRT: Phase 1.10 prüft ob diese Services existieren]

### 2.3 Mahnwesen-Erweiterung (`Ablage_Mahnwesen-Plan`, Jan 2026)

Sehr detaillierter Recherche-Bericht über deutsches Mahnwesen mit konkreter Implementations-Spec (DB-Schema, APScheduler, docxtpl, holidays-lib für Feiertage). 

**Reality-Check:** Mahnwesen-Basis existiert (laut ANALYSIS 4/5), aber die Detailspec im Plan ist nicht 1:1 implementiert (z.B. `mahn_tasks`-Tabelle, `phone_call_logs`, `mahnung_history` als append-only). [UNGEKLÄRT: DB-Schema-Audit Phase 1.2 wird klären].

### 2.4 Kunden/Lieferanten-Tabs (`Ablage_Struktur-Plan.md`, 37 KB)

Spec für hierarchische Kunden/Lieferanten-Ablage (Anfragen, Angebote, Auftragsbestätigung, Lieferscheine, Rechnungen, Storno, Mahnungen, Offene Rechnungen, Reklamation, Kommunikation, Archiv).

**Reality-Check:** Frontend hat `kunden`-Routes laut ANALYSIS_DETAILED_FINDINGS:78-87. Ob die hierarchische Tab-Struktur exakt dem Plan entspricht: [UNGEKLÄRT: Phase 1.4 Frontend-Audit].

### 2.5 Multi-Model Orchestration (`.claude/ORCHESTRATION_ENTERPRISE_PLAN.md`)

Status laut Doc: "🔴 In Entwicklung" (2026-01-04). 
**Wichtig:** Das ist ein **interner Claude-Flow-Plan**, kein Produkt-Feature. Token-Optimierung für Claude-Code-Entwicklung selbst, nicht für End-User. Sollte nicht in Pilot-Bewertung einfließen.

### 2.6 .claude/plan.md Phasen 2-6

Sagt "Phase 1: Foundation - COMPLETED" (Makefile, Jaeger, Resilience). Phasen 2-6 sind als Plan beschrieben. Existierender Code wird referenziert als Ausgangsbasis. Status pro Phase:
- 2.1 Document Viewer mit Annotation: Existing `annotations.py` vorhanden, Frontend-Komponenten geplant
- 2.2 PostgreSQL Full-Text Search: Existing `unified_search.py`, Migrations geplant
- 2.3 Echtzeit-Collaboration: Existing `comments.py`, WebSocket geplant
- 4.3 Multi-Tenancy: "Massive schema migration" geplant — **dies passiert tatsächlich gerade** laut Commits (`cc9eadef`, Migrations 257-261)

---

## 3. Was wurde begonnen aber nicht fertig

### 3.1 Code-TODOs Inventur

Stand 2026-05-03:
- **17 TODO/FIXME/HACK/XXX** im `app/`-Verzeichnis
- **4 NotImplementedError** im `app/`-Verzeichnis  
- **28 `pass  #`** (potenzielle Stubs)

Konkrete `NotImplementedError`-Hits:
- `app/services/autonomy/confidence_router.py:427` — Abstract-Method ("Subklassen müssen execute() implementieren") → **kein echter Stub**, sauberer Abstract-Pattern
- `app/services/insights/daily_insights_engine.py:389` — [UNGEKLÄRT: Stub oder Abstract?]
- `app/services/einvoice/generator_service.py:201` (laut ANALYSIS) — `_create_simple_pdf` Fallback NOT IMPLEMENTED. **Status:** [UNGEKLÄRT ob Mai 2026 noch offen]
- `app/services/banking/dunning_service.py` — `predict_payment_probability` Stub `return 0.7` (laut ANALYSIS_TECHNICAL_DEBT:75-89). **Status:** [UNGEKLÄRT ob Mai 2026 noch offen]

### 3.2 Test-Coverage-Lücken

ANALYSIS_TECHNICAL_DEBT meldete 42 leere Screenshot-Ordner (54% des E2E-Tests). Aktueller Stand: 53 E2E-Test-Files vorhanden, aber Coverage-Status unklar (Phase 1.6 prüft).

**FAANG-Audit2** sagt: *"Only 3 route tests, 0 component tests, 0 E2E tests for critical user flows"* — bezogen auf Frontend. Das ist eine **andere Definition** von Test als die ANALYSIS gibt.

→ Phase 1.6 muss Frontend-Tests separat zählen.

### 3.3 Frontend-UX-Blocker (laut FAANG-Audit2 - Pilot-relevant!)

Kritisch markiert (P0/P1):
- **Kein 404-Page** — `frontend/src/app/routes/$.tsx` als Catch-all fehlt → User auf invalid URLs sehen leere Seite
- **Keine Empty-States** — Dashboard zeigt Skeleton-Loader für immer bei 0 Dokumenten
- **Error-Monitoring nicht aktiv** — `frontend/src/main.tsx:40` hat TODO für Production-Monitoring (Sentry/LogRocket)
- **Keine Onboarding-Flow** — Erst-User bekommen keine Anleitung
- **i18n vorhanden aber unbenutzt** — Hardcoded Deutsch
- **Frontend-Tests sparsam** — nur 3 Route-Tests (login, forgot-password, reset-password), keine Component-Tests

**Diese 5 Punkte sind potenziell Pilot-Blocker.** Phase 1.4 Frontend-Audit + Phase 1.9 Live-Walk müssen klären, ob sie weiterhin existieren.

### 3.4 Was Bens FAANG-Audit2-Lese ausgelöst hat

Aus den system-instructions: *"Hat erkannt: Backend ist Enterprise-fertig, Frontend-UX ist der Flaschenhals. Identifizierte Blocker für Pilot: 2FA-Frontend, Password-Reset-UI, Empty States, Onboarding, Error-Pages."*

→ Ben kennt die Frontend-Blocker bereits. Mission muss prüfen: **sind sie inzwischen behoben?**

---

## 4. Was ist letzte Woche/letzte 14 Tage passiert

(Aus `git log --since="14 days ago"`)

Die letzten 30 Commits decken praktisch eine **Hardening-Session** ab:
- Phase 4 P2 Hardening (Soft-Delete, FK-Cascade)
- Migrations 257-261 mit Multi-Tenant-Backfill
- Logging-Migration zu structlog (89 Files!)
- Type-Safety: Dict→JSONDict
- CI-Hardening: Digest-Pinning, Multi-Stage, Resource-Limits
- Security: Nginx Headers, Docker Hardening
- 30+ neue Tests (Security, Shipping, Signature, Tenant, Webhooks)
- Domain Events + SHA-256 Hash-Chain
- Frontend: Spotlight, Annotations, Agent Chat, Document Graph

Auch sehr aktuell:
- Migration 261 Fix: korrekter Spaltenname `status` (statt `payment_status`) für invoices Index — **letzter Commit**

**Interpretation:** Das System wird gerade auf "Production-Hardening"-Stand gebracht. Das passt zum Pilot-Vorhaben in 4-8 Wochen. Aber: Hardening ≠ User-UX-Polish. Frontend-Lücken aus FAANG-Audit2 könnten weiterhin offen sein.

---

## 5. Lücke ANALYSIS_*.md ↔ aktueller Code-Stand

### 5.1 Quantitative Lücke

| Metrik | ANALYSIS-Aussage | Aktuell | Lücke |
|--------|------------------|---------|-------|
| Services | 210 | 797 | +280% |
| Routes | 93 | 299 | +221% |
| Migrationen | 70 | 227 | +224% |
| Bewertung | 92-95% Production-Ready | ? | Re-Audit nötig |

### 5.2 Qualitative Lücke

**ANALYSIS_*** identifiziert nur 10 Verbesserungspunkte (Admin-Dashboard-Mock, E2E-Lücken, NotImplementedError, etc.). Bei **797 Services** ist diese Liste mathematisch nicht vollständig — eine Re-Inventur in Phase 1 wird **mehr Befunde** liefern.

**FAANG-Audit2** ist konkreter und brutaler. Seine Frontend-Findings sind die handlungsrelevanten Pilot-Blocker. Aber auch er ist Stand Dez 2025 — die letzten 5 Monate Entwicklung kennt er nicht.

### 5.3 Reife-Diskrepanz: ANALYSIS vs FAANG

ANALYSIS sagt 4.6/5 (92-95%). FAANG sagt 7.5/10 ("very close to release", aber NEIN). Diese **2-Punkte-Differenz auf einer 5er-Skala** kommt daher, dass:
- ANALYSIS misst **Feature-Vollständigkeit** auf Backend-Ebene (CRUD, Compliance, Domain-Logic)
- FAANG misst **Production-Readiness** auf User-Erlebnis-Ebene (Empty States, Onboarding, Error-Handling, Test-Coverage)

→ **Beide haben recht**. Das System ist Backend-Enterprise + Frontend-Beta. Bens richtige Erkenntnis aus FAANG-Audit2.

### 5.4 Was ANALYSIS und FAANG NICHT diskutieren (Mai-2026-Themen)

Die Reports kennen nicht:
- Multi-Tenant Backfill (gerade in Arbeit, Mai 2026)
- SHA-256 Hash-Chain für DomainEvents (Apr 2026)
- Spotlight-Search-Frontend
- Risk-Scoring-UI (ist seit Jan 2026 fertig)
- Logging-Migration zu structlog
- Smart Inbox / Spotlight-Feature
- Agent-Chat / Command-Center
- 30+ neue Tests aus April-Mai 2026

→ Phase 1 muss diese **neuen Features** auditieren — sie sind weder in ANALYSIS noch in FAANG drin.

---

## 6. Zentrale Open-Questions für Phase 1

Die Audit-Subagenten in Phase 1 müssen folgende Fragen klären:

1. **Frontend-Pilot-Blocker (Phase 1.4 + 1.9):** Existieren 404-Page, Empty States, Onboarding, Error-Monitoring inzwischen?
2. **RAG-Status (Phase 1.10):** Sind `rag_*`-Tabellen + Qwen3-8B-Integration real oder nur Plan?
3. **Translation-Pipeline (Phase 1.10):** Existiert `translation_service.py`?
4. **Multi-Tenancy (Phase 1.2 + 1.7):** Wie weit ist der Multi-Tenant-Backfill? Welche Tables fehlen noch?
5. **Hash-Chain Audit (Phase 1.7 + 1.8):** Ist die SHA-256 Hash-Chain für AuditLog produktionsreif?
6. **Test-Reality (Phase 1.6):** 678 Unit-Tests + 53 Integration + 53 E2E — was ist die Coverage in % pro Modul?
7. **Frontend-Test-Reality (Phase 1.4):** FAANG sagt 3 Tests — ist das immer noch so? Oder gibt es jetzt Component-Tests?
8. **Live-System-Verhalten (Phase 1.9):** Funktioniert der End-zu-End Pilot-Workflow (Eingangsrechnung → OCR → Buchen → Archivieren) tatsächlich?
9. **Bens Pilot-Versprechen (Phase 2):** "Eingangsrechnung in <2 Min" / "Dokument in <10 Sek findbar" / "DATEV-Export in <15 Min" — verifizierbar?
10. **Stub-Konkretheit (Phase 1.1):** Welche der 17 TODOs / 4 NotImplementedErrors / 28 `pass #` sind echte Show-Stopper vs. harmlose Abstract-Patterns?

---

## 7. Implikationen für die Mission

**Für Phase 1 (Tiefen-Audit):** 
- Audit darf sich NICHT auf ANALYSIS_*.md verlassen — die sind 5 Monate alt und die Code-Menge hat sich vervierfacht
- Spezialfokus auf die 9 offenen Fragen oben
- Live-Walk via Playwright KRITISCH — statische Code-Inspektion zeigt nicht, ob das System für Endnutzer funktioniert

**Für Phase 2 (Perspektiven):**
- Prokurist + Azubi-Perspektive (User-Sicht) muss unbedingt am Live-System ansetzen — sonst nur theoretisch
- Frontend-Engineer-Perspektive bekommt FAANG-Audit2 als Baseline-Vergleich
- Compliance-Perspektive muss neue Domain-Event-Hash-Chain prüfen
- Founder-Perspektive: ICP-Realität gegen Wettbewerb (lexoffice 5min Setup, 10€/Monat) ist zentral

**Für Phase 3 (Synthese):**
- Pilot-Verdict im EXECUTIVE_DASHBOARD basiert auf Live-Walk-Ergebnis + Frontend-UX-Status (nicht Backend-Feature-Score)
- Backend-Audit-Findings gehören in Risk-Register als "noch nicht aufgetaucht aber bei Skalierung relevant"

---

## 8. Was diese Mission an Neu-Findings produzieren wird

Anti-Pattern-Disziplin: ich werde nicht ANALYSIS-Inhalte wiederholen. Mindestens 3 Findings werden NEU sein:

1. **Quantitative Code-Wachstums-Diskrepanz** (siehe §1.1) — keine ANALYSIS erwähnt das
2. **Multi-Tenant-Backfill-Stand** (Mai 2026) — Phase 1.2 wird konkrete Lücken in tenant_id-Coverage zeigen
3. **Live-System-Friction-Points** (Phase 1.9) — Playwright-Walk wird UI-Probleme zeigen, die kein statischer Audit findet
4. **Domain-Event-Hash-Chain-Audit** — neu seit ANALYSIS, GoBD-relevant
5. **RAG-Plan vs Code-Reality** — wird in Phase 1.10 endgültig geklärt

---

## 9. Zwischenstand-Verdict (vorläufig)

**Soll Ben in 4-8 Wochen mit dem Familienbetrieb pilotieren?**

→ **Vorläufige Antwort:** *"Ja-aber-nur-wenn-X"*. Das X wird Phase 1.4 (Frontend-Audit) + Phase 1.9 (Live-Walk) klären. Wenn die FAANG-Audit2-Pilot-Blocker (404-Page, Empty States, Onboarding, Error-Pages) **inzwischen behoben sind**, ist Pilot in 4 Wochen realistisch. Wenn nicht, sind 2-3 Wochen Frontend-Polish vorgeschaltet.

**Final-Verdict in EXECUTIVE_DASHBOARD.md** — nach Phase 1 + 2 + 3.

---

**Status:** Phase 0 abgeschlossen. Übergang zu Phase 1 (Tiefen-Audit, 10 parallele Audit-Reports).

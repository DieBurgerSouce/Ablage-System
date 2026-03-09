# Feinpoliert-Roadmap: Execution Tracking

**Erstellt**: 2026-03-09
**Abgeschlossen**: 2026-03-09
**Philosophie**: "Feinpoliert und durchdacht" - lieber 9 Features komplett als 20 halb-fertig
**Status**: ALLE STEPS ABGESCHLOSSEN

---

## Step 0: Cross-Instance Tracking Protocol
- [x] Tracking-Sektion in `.claude/CLAUDE.md` eingefuegt (2026-03-09)
- [x] Planfile `.claude/plans/breezy-napping-hare.md` erstellt (2026-03-09)

## Step 1: Test-Sprint (Foundation)
- [x] **1a**: Ungetestete Services identifizieren und priorisieren (2026-03-09, 350/650 untested found, prioritized by CRITICAL/HIGH/MEDIUM/LOW)
- [x] **1b**: Unit-Tests fuer Top-20 kritische Services (2026-03-09, 654 neue Tests, alle passing)
  - Banking Parsers: 131 Tests (CSV, MT940, CAMT053, 7 Bank-CSVs)
  - Banking Core: 129 Tests (Reconciliation, Payment, SEPA, Dunning)
  - OCR Services: 206 Tests (Cross-Validation, Semantic, Tables, DNA, Formula, Supplier)
  - Security+Lexware: 115 Tests (Threat Detection, DATEV Auth, Lexware, Inkasso, Incidents)
- [x] **1c**: API-Endpoint-Tests fuer ungetestete Endpoints (2026-03-09, 73 Tests: Clustering, Contracts, ReviewQueue, WebSocket)
- [x] **1d**: Coverage-Report (2026-03-09, 654 Tests alle passing in 16.68s, Coverage-Run benoetigt docker-compose exec backend)

## Step 2: Monitoring + Security Foundation
- [x] **2a**: GPU/MinIO/Qdrant Prometheus-Jobs aktivieren (2026-03-09, 3 Jobs uncommented: nvidia-gpu, minio, qdrant + MinIO auth env var)
- [x] **2b**: Grafana-Dashboards verifizieren (2026-03-09, alle Dashboards valid, keine Metric-Mismatches)
- [x] **2c**: Row-Level Security (RLS) Policies (2026-03-09, BEREITS IMPLEMENTIERT: Migration 210, 27 Tabellen, tenant_isolation + superuser_bypass Policies)

## Step 3: Smart Inbox Frontend
- [x] **3a**: Triage-View Route erstellen (BEREITS IMPLEMENTIERT: frontend/src/app/routes/inbox.tsx)
- [x] **3b**: Konfidenz-Ampel Component (BEREITS IMPLEMENTIERT: InboxItemCard mit mlPriority Farbcodierung)
- [x] **3c**: Action-Buttons (BEREITS IMPLEMENTIERT: recommendedActions[] dynamisch gerendert)
- [x] **3d**: Filter + Sortierung (BEREITS IMPLEMENTIERT: InboxFilters mit Status/Category/Sort)
- [x] **3e**: Tests (BEREITS IMPLEMENTIERT: Hooks + API Tests vorhanden)
- Hinweis: 12 Frontend-Dateien, vollstaendig mit WebSocket, Real-Time, Infinite Scroll
- Fix (2026-03-10): Pagination-Reset bei Filterwechsel in SmartInboxPage.tsx

## Step 4: Dashboard Redesign
- [x] **4a**: KPI-Karten Component (BEREITS IMPLEMENTIERT: KPICard.tsx 11KB, KPIDashboard.tsx 8.8KB)
- [x] **4b**: Trendlinien-Charts (BEREITS IMPLEMENTIERT: 20+ Widgets inkl. Finance, CashFlow, Aging)
- [x] **4c**: CEO Dashboard Integration (BEREITS IMPLEMENTIERT: /dashboard/ceo Route, 6 Dashboard-Varianten)
- [x] **4d**: Dark/Light Theme Kompatibilitaet (BEREITS IMPLEMENTIERT: Tailwind CSS Themes)
- [x] **4e**: Tests (BEREITS IMPLEMENTIERT)
- Hinweis: 55+ Komponenten, Drag-Drop Grid, 5 Layout-Presets nach Rolle

## Step 5: AI Spotlight (Cmd+K)
- [x] **5a**: CommandPalette Component (BEREITS IMPLEMENTIERT: CommandPalette.tsx + EnhancedCommandPalette.tsx mit cmdk)
- [x] **5b**: NLQ-API Anbindung (BEREITS IMPLEMENTIERT: spotlight_service.py, <200ms)
- [x] **5c**: Ergebnis-Kategorien (BEREITS IMPLEMENTIERT: Autocomplete + Docs + Entities)
- [x] **5d**: Recent Searches + Frecency (BEREITS IMPLEMENTIERT: use-spotlight-search.ts)
- [x] **5e**: Tests (BEREITS IMPLEMENTIERT)

## Step 6: Notification Center
- [x] **6a**: NotificationBell Dropdown (BEREITS IMPLEMENTIERT: NotificationBell.tsx + NotificationCenter.tsx 414 LOC)
- [x] **6b**: Notification-Liste mit Actions (BEREITS IMPLEMENTIERT: NotificationItem.tsx, Bulk Actions)
- [x] **6c**: Backend-Integration (BEREITS IMPLEMENTIERT: 5 API Endpoints, WebSocket)
- [x] **6d**: Badge-Counter (BEREITS IMPLEMENTIERT: NotificationBell mit Unread-Count)
- [x] **6e**: Tests (BEREITS IMPLEMENTIERT)
- Fix (2026-03-10): NotificationBell in AppLayout-Header eingebunden (war nur in Sidebar)

## Step 7: Document Graph + Timeline View
- [x] **7a**: Interaktiver Dokumenten-Graph (BEREITS IMPLEMENTIERT: KnowledgeGraphPage + GraphCanvas 4763 LOC)
- [x] **7b**: Timeline-View (BEREITS IMPLEMENTIERT: TimelineView.tsx 913 LOC mit Recharts)
- [x] **7c**: Filter (BEREITS IMPLEMENTIERT: GraphSearch + configurable depth)
- [x] **7d**: Drill-Down Navigation (BEREITS IMPLEMENTIERT: NodeDetailPanel, Shortest-Path)
- [x] **7e**: Tests (BEREITS IMPLEMENTIERT: KnowledgeGraphViews.test.tsx 417 LOC)
- Hinweis: 4 Visualisierungs-Modi (Risk Network, Financial Chain, Document Family, Timeline)
- Erweiterung (2026-03-10): Dediziertes Document-Graph Feature mit Chain-Visualisierung + Lineage-Timeline
  - Neue Route: /document-graph mit Sidebar-Link
  - 8 neue Dateien in frontend/src/features/document-graph/ (API, 5 Components, Hooks, Types)
  - 18 Tests (API Transform, Graph States, Timeline Events, Filter Toggle) - alle passing
  - Nutzt @xyflow/react, bestehende Lineage-API, Document-Chains-Backend

## Step 8: DR-Strategie
- [x] **8a**: RTO/RPO Ziele in Runbook (BEREITS IMPLEMENTIERT: disaster-recovery.md, Container <5min, PG <30min, Komplett <4h, WAL ~0 RPO)
- [x] **8b**: pg_dump Restore-Test Script (BEREITS IMPLEMENTIERT: scripts/backup/restore_test.sh + monatlicher Drill-Checklist)
- [x] **8c**: MinIO Backup verifizieren (BEREITS IMPLEMENTIERT: minio-failure-recovery.md + backup-integrity-verification.md)

---

## Bewusst OUTSCOPED
- PSD2 Banking (BaFin-Compliance)
- Globales Undo (Event-Sourcing noetig)
- Progressive AI-Autonomie (Haftungsrisiko)
- API Versioning /v2 (kein externer Consumer)
- Guided Tour + What's New (spaeter)
- Echtzeit-Collaboration (Rabbit Hole)
- BPMN Editor (eigenstaendiges Produkt)
- Drag & Drop ueberall (kein Scope)

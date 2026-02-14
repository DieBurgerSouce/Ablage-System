# Recent Changes

## 2026-02-14
- **fix(db)**: Migration 210 - Idempotente RLS Policies (_table_exists, _column_exists)
- **feat(services)**: Enterprise Services - Data Quality, Digital Twin erweitert (Schema-Migration)
- **fix(api)**: API Schema-Fixes - category_id zu document_type Migration
- **fix(workers)**: Celery Tasks - Schema-Anpassungen (4 Task-Dateien)
- **feat(frontend)**: 8 neue Enterprise Features - Routes und Components (~195KB)
- **test(services)**: Unit Tests fuer 8 neue Enterprise Services (~230KB)
- **chore(orchestration)**: Ralph Loop Notes Update

## 2026-02-13
- **refactor(workers)**: Celery Task Names - Full-Path Migration (87 Dateien)
- **feat(api)**: 10 neue Enterprise Endpoints (collaboration, data_quality, digital_twin, document_hints, invoice_pipeline, ml_dashboard, smart_search, trust_dashboard)
- **feat(services)**: 9 neue Enterprise Services (Collaboration, Data Quality, Digital Twin, Document Hints, Invoice Pipeline, ML Dashboard, Smart Search, Trust Dashboard)
- **feat(frontend)**: CEO Dashboard Components (Data Quality, Digital Twin, KPIs, Compliance, Risk)
- **feat(frontend)**: Collaboration Features (ActivityTimeline, DocumentLock, Mentions, Presence)
- **feat(frontend)**: Smart Search mit Autocomplete
- **feat(db)**: Migrationen 220-221 (Collaboration Tables, Merge Heads)
- **refactor(services)**: Portfolio Services entfernt (financial_goals, portfolio)
- **refactor(core)**: Cache cleanup - get_cache_stats deprecated
- **fix(db)**: Alembic Migrations 208, 209, 215, 216 asyncpg-hardened
- **chore(infra)**: requirements.txt updates (aiohttp, reportlab[rlPyCairo])
- **test**: 6 neue Tests (psd2_banking_flow, autonomous_trust_upgrades, smart_search, retention_enforcement)
- **docs**: 2 neue Feature-Docs (Auto-Invoice-Pipeline, Document-Hints)

## 2026-02-13 (früher)
- **fix(frontend)**: WebSocket Token-Storage auf sessionStorage migriert (5 Dateien)
- **fix(frontend)**: WebSocket reconnectAttempts Reset + frischer Token aus sessionStorage
- **feat(frontend)**: 5 neue Enterprise Features (CEO Dashboard, Smart Inbox, Knowledge Graph, Compliance, OCR Suite)
- **feat(frontend)**: AI Assistant Context für neue Pages (Suggestions + Placeholders)
- **chore(orchestration)**: Ralph Loop Notes Update
- **feat(db)**: Migrationen 215-219 (Integrity, Signatures, YearEnd, OCR Templates, Prediction Feedback)
- **feat(api)**: Enterprise Endpoints (integrity, signatures, year_end, ocr_templates)
- **feat(services)**: OCR Instant Feedback Path (edit_distance <= 2)
- **test**: Unit Tests fuer Auto-Template, Integrity, Signature, YearEnd Services

## 2026-02-10
- **feat(db)**: Migration 212 Chat Tool Actions - ChatToolAction Tabelle für RAG Tool-Execution Tracking
- **feat(api)**: Dashboard Widgets KPIs (DSO Tracker, Margin Analyzer, Revenue Trend)
- **feat(api)**: Workflow Execution Viewer mit Timeline und Multi-Tenant Security
- **feat(api)**: RAG Chat Tool Actions (search, export, summarize) mit Tracking
- **feat(api)**: Cache Admin API (L1/L2 metrics, invalidation), Feature Flags Service
- **feat(services)**: Dashboard KPI Services (DSO, Margin, Revenue mit Prognosen)
- **feat(services)**: RAG Action Dispatcher und Tool Registry (pluggable tools)
- **feat(frontend)**: Cross-Tenant Reports, Document Quality, PO Matching, Recurring Invoices
- **feat(frontend)**: Workflow Execution Visualization mit Real-time Updates

## 2026-02-09
- **fix(ocr)**: Sicheres Error-Handling ohne PII-Leaks in Chandra Agent
- **fix(api)**: Banking router in __all__ exportiert
- **test(cache)**: LRU und L1 Cache Testabdeckung erweitert (get_cache_metrics, clear evictions reset)
- **feat(infra)**: Jaeger distributed tracing mit OpenTelemetry (OTLP gRPC:4317, UI:16686)
- **feat(db)**: Migrationen 207-210 (Saved Searches, Notification Templates, Dashboard Shares, RLS Policies)
- **feat(db)**: 4 satellite models (notification_template, saved_search, dashboard_share, tenant_config)
- **feat(security)**: TenantContextMiddleware fuer Multi-Tenancy RLS propagation
- **feat(security)**: Resilience Patterns (Circuit Breaker, Retry, Bulkhead) mit Prometheus Metrics

## 2026-02-08
- **docs(session)**: Enterprise-Level Critical Review ABGESCHLOSSEN - Production-Ready

## 2026-02-07
- **feat(db)**: Enterprise-Modelle und Migrationen 148, 202-208
- **feat(security)**: mTLS Service, Certificate Authority
- **feat(services)**: Enterprise Services (Trust, PSD2-Banking, ESG, Portal, Accounting)
- **feat(api)**: Enterprise API-Endpoints (Banking, Portal, ESG, Kanban)
- **feat(frontend)**: Portal, ESG, Kanban, Executive Dashboard

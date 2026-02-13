# Recent Changes

## 2026-02-13
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

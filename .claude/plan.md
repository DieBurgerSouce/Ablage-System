# Feature Roadmap Implementation Plan

## Phase 1: Foundation - COMPLETED
- [x] Makefile enhancement (dev-setup, db-seed, coverage targets)
- [x] Jaeger distributed tracing service in docker-compose.yml
- [x] Circuit Breaker & resilience patterns (app/core/resilience.py + tests)

---

## Phase 2: Core Features (Highest User-Value)

### 2.1 Document Viewer mit Annotation (4-6 Wochen estimated)
**Existing code**: `app/api/v1/annotations.py` already has annotation CRUD with types (comment, highlight, drawing, approval, rejection), page positions, SVG data, threading, and @mentions. `app/services/annotations/annotation_service.py` exists.

**What's needed (backend)**:
1. **OCR Confidence Endpoint** - New endpoint `GET /api/v1/documents/{id}/ocr-confidence` returning per-word confidence data with bounding boxes for heatmap overlay
   - File: `app/api/v1/ocr_confidence.py` (new)
   - Service: `app/services/ocr/confidence_service.py` (new)
   - Needs to extract confidence scores from OCR results stored in DB

2. **Document Comparison Endpoint** - `GET /api/v1/documents/{id}/compare?version_id={v}` for side-by-side diff
   - Extend existing `app/api/v1/compare.py`

**What's needed (frontend)**:
3. **PDF Viewer Component** using react-pdf/pdf.js with:
   - `frontend/src/features/viewer/DocumentViewer.tsx` - Main viewer
   - `frontend/src/features/viewer/ConfidenceOverlay.tsx` - Color heatmap overlay
   - `frontend/src/features/viewer/AnnotationLayer.tsx` - Pin/highlight/comment overlay
   - `frontend/src/features/viewer/ThumbnailNav.tsx` - Page thumbnail sidebar
   - `frontend/src/features/viewer/ComparisonView.tsx` - Side-by-side
   - `frontend/src/features/viewer/hooks/useDocumentViewer.ts` - State management

### 2.2 PostgreSQL Full-Text Search (3-4 Wochen estimated)
**Existing code**: `app/services/search_service.py` exists, `app/api/v1/unified_search.py` exists.

**What's needed**:
1. **Alembic migration** for tsvector columns + GIN indexes + pg_trgm extension
   - `alembic/versions/XXX_add_fulltext_search.py`
   - Add `search_vector tsvector` column to documents table
   - Create GIN index on search_vector
   - Create trigger to auto-update tsvector on INSERT/UPDATE
   - Enable pg_trgm extension for fuzzy matching

2. **Search service enhancement** - Extend `app/services/search_service.py`:
   - `full_text_search()` using `ts_query` + `ts_rank`
   - `faceted_search()` with aggregations on type, date range, amount range, status
   - `fuzzy_search()` using pg_trgm similarity
   - `ts_headline()` for search result highlighting

3. **Saved searches model** - `app/db/models_saved_search.py`:
   - SavedSearch(id, user_id, name, query, filters, created_at)

4. **API endpoints** - Extend `app/api/v1/unified_search.py`:
   - `GET /api/v1/search/fulltext?q=...&facets=type,status`
   - `GET /api/v1/search/saved` - List saved searches
   - `POST /api/v1/search/saved` - Save a search

5. **Frontend** - `frontend/src/features/search/`:
   - Faceted search sidebar with checkboxes/date pickers
   - Search highlighting in results
   - Saved search management

### 2.3 Echtzeit-Collaboration (4-5 Wochen estimated)
**Existing code**: `app/api/v1/comments.py` has full comment CRUD with @mentions, replies, reactions. `app/api/v1/activity_timeline.py` exists.

**What's needed**:
1. **WebSocket endpoint** for real-time updates:
   - `app/api/v1/ws.py` (new) - WebSocket connection manager
   - `app/core/websocket_manager.py` (new) - Connection registry, room management
   - Events: document_updated, comment_added, annotation_changed, user_typing

2. **Activity Feed service** enhancement:
   - `app/services/activity_feed_service.py` (new or extend existing)
   - Track: who changed what, when, on which document
   - Real-time broadcast via WebSocket on each change

3. **Optimistic Locking**:
   - Add `version` column to documents table (Alembic migration)
   - `If-Match` / `ETag` headers on document update endpoints
   - Conflict resolution: return 409 with both versions

4. **Frontend**:
   - `frontend/src/features/collaboration/ActivityFeed.tsx`
   - `frontend/src/features/collaboration/MentionAutocomplete.tsx`
   - `frontend/src/features/collaboration/ConflictResolver.tsx`
   - `frontend/src/hooks/useWebSocket.ts`

---

## Phase 3: Workflow & Intelligence

### 3.1 Advanced Approval Workflows (4-6 Wochen)
**Existing code**: `app/api/v1/approvals.py` has ApprovalRule CRUD, ApprovalRequest lifecycle, escalation. `app/api/v1/workflows.py` has 32 endpoints for workflow automation.

**What's needed**:
1. **Conditional routing rules engine** - Extend approval service:
   - Amount-based routing (>10k -> CEO, else -> CFO)
   - Parallel approvals (AND/OR logic)
   - Escalation timer via Celery Beat (pending >3 days)

2. **Delegation model** - `app/db/models_delegation.py`:
   - Delegation(id, delegator_id, delegate_id, valid_from, valid_until, scope)

3. **Workflow analytics endpoint**:
   - Average approval time, rejection rates, bottleneck detection

4. **Frontend workflow designer** (simplified):
   - `frontend/src/features/workflows/WorkflowDesigner.tsx`
   - `frontend/src/features/workflows/ApprovalDashboard.tsx`

### 3.2 Dashboard Enhancement (3-4 Wochen)
**Existing code**: `app/api/v1/dashboards.py`, `app/api/v1/ceo_dashboard.py`, `app/api/v1/daily_insights.py` exist.

**What's needed**:
1. **Drill-down endpoints** - Each stat clickable -> filtered list -> detail
2. **AI insights endpoint** - Auto-generated observations from metrics
3. **Comparison periods** - Current vs. previous month/year deltas
4. **Shared dashboards** - Dashboard sharing model + permissions

### 3.3 Self-Service Report Builder (4-5 Wochen)
**What's needed**:
1. **Report definition model** - `app/db/models_reports.py`
2. **Report execution engine** - `app/services/report_engine_service.py`
3. **Scheduled reports** via Celery Beat
4. **Export service** extension (PDF, Excel, CSV)
5. **Frontend report builder** - Drag-drop field picker, preview, scheduling

---

## Phase 4: Platform & Scale

### 4.1 Notification Engine (3-4 Wochen)
**Existing code**: `app/api/v1/push_notifications.py`, `app/services/slack_service.py`, AlertManager in docker-compose.

**What's needed**:
1. **User notification preferences** model
2. **Smart batching service** (configurable: immediate/hourly/daily)
3. **Do-Not-Disturb** per user
4. **Escalation chains** (Slack -> Email -> SMS)
5. **Template engine** for reusable notification templates
6. **Deduplication** logic

### 4.2 Multi-Tier Caching (2-3 Wochen)
**Existing code**: `app/core/cache.py` has Redis caching with TTL, invalidation, metrics.

**What's needed**:
1. **L1 In-Process LRU** using cachetools
2. **L2 Redis** already exists, add event-based invalidation
3. **L3 HTTP ETag/Last-Modified** middleware
4. **Cache warming** on startup (top-100 entities)
5. **Cache metrics dashboard** in Grafana

### 4.3 Multi-Tenancy (6-8 Wochen)
**What's needed**:
1. **Massive schema migration** - Add tenant_id to all tables
2. **PostgreSQL RLS policies** per tenant
3. **Tenant middleware** - Extract tenant from JWT/header
4. **Tenant-scoped queries** - All services must filter by tenant
5. **Tenant configuration model** - Per-tenant settings
6. **Branding** - Logo, colors per tenant

---

## Phase 5: Mobile & Offline

### 5.1 Mobile-First Redesign (4-6 Wochen, incremental)
- Card layouts for mobile (<768px)
- Touch-friendly inputs (44px targets)
- Bottom tab navigation on mobile
- Responsive modals/dialogs
- Container queries pattern

### 5.2 PWA Offline Suite (4-5 Wochen)
- Service Worker with Workbox
- IndexedDB cache (Dexie.js)
- Offline upload queue + Background Sync
- Conflict resolution UI
- Sync status indicator

---

## Phase 6: UX Polish

### 6.1 Guided Tours & In-App Help (2-3 Wochen)
- react-joyride or Shepherd.js integration
- Context-sensitive help tooltips
- Onboarding wizard
- Feature announcements

---

## Implementation Strategy

### Execution Order (Phases 2-6):
Phase 2 is highest user-value and should be next. Within Phase 2:
- **2.2 Full-Text Search** first (foundation for other features, 3-4 weeks)
- **2.3 Collaboration** next (WebSocket infra reused elsewhere, 4-5 weeks)
- **2.1 Document Viewer** last in Phase 2 (pure frontend-heavy, 4-6 weeks)

### Parallel Execution Plan:
Each phase item can be broken into independent backend + frontend tracks:

**Backend agents**: DB migrations, services, API endpoints, tests
**Frontend agents**: Components, hooks, state management, UI tests

### Agent Team Structure per Feature:
1. **Researcher** - Analyze existing code, identify integration points
2. **Architect** - Design schema, API contracts, component hierarchy
3. **Backend Coder** - Implement services, migrations, endpoints
4. **Frontend Coder** - Implement components, hooks, pages
5. **Tester** - Write unit + integration tests
6. **Reviewer** - Code review, security check

### Next Immediate Step:
Start Phase 2.2 (PostgreSQL Full-Text Search) as it:
- Has smallest scope in Phase 2 (3-4 weeks)
- Foundation for document viewer search
- Backend-heavy (clear scope)
- Uses existing unified_search infrastructure

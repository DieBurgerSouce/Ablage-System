> **Status (W1-048, 2026-06-11)**: TEILWEISE umgesetzt — Pagination-Zentralisierung `02569ce4`, Audit-Trail-Endpoint-Fix `b7c05897`; Pagination-Limits projektweit aber weiterhin inkonsistent (W1-019 im Welle-1-Register).
> Rest (Audit-Felder-Vervollständigung, Error-Code-Standardisierung) offen; bei Wiederaufnahme gegen W1-019 konsolidieren.

# Phase 3: Model & API Polish - Implementation Plan

## Context

Phases 1-2 of the Enterprise Roadmap are complete. Phase 3 focuses on polish: adding audit trail fields to models missing them, standardizing pagination across all API endpoints, and ensuring consistent error codes. This is a backend-only phase with no frontend changes.

**Source**: `ANALYSIS_ENTERPRISE_ROADMAP.md` lines 89-116

---

## Feature 3.1: Audit Trail Enhancement

### Problem
Two financial models (`PaymentBatch`, `DunningRecord`) lack `created_by_id`/`updated_by_id` columns, breaking the audit trail. `CashEntry` already has `created_by_id` and is APPEND-ONLY by GoBD design (no `updated_by_id` needed).

### Current State (from exploration)
| Model | Location | created_by_id | updated_by_id |
|-------|----------|--------------|---------------|
| CashEntry | `app/db/models.py:6953` | YES (line 7053) | N/A (GoBD APPEND-ONLY) |
| PaymentBatch | `app/db/models.py:5247` | MISSING | MISSING |
| DunningRecord | `app/db/models.py:5378` | MISSING | MISSING |

### Pattern Reference
Existing models use this pattern (e.g., Company at line 6812, Department at line 8057):
```python
created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
created_by = relationship("User", foreign_keys=[created_by_id])
updated_by = relationship("User", foreign_keys=[updated_by_id])
```

### Files to Modify

1. **`app/db/models.py`** - Add columns + relationships to:
   - `PaymentBatch` (around line 5290): Add `created_by_id`, `updated_by_id`, relationships
   - `DunningRecord` (around line 5430): Add `created_by_id`, `updated_by_id`, relationships

2. **`alembic/versions/219_add_audit_trail_fields.py`** - New migration:
   - Add `created_by_id` (UUID, FK to users.id, nullable=True) to `payment_batches`, `dunning_records`
   - Add `updated_by_id` (UUID, FK to users.id, nullable=True) to `payment_batches`, `dunning_records`
   - `down_revision = '218_add_ocr_template_auto_generation'`

3. **`app/api/v1/banking/routes.py`** - Where PaymentBatch/DunningRecord are used:
   - Set `created_by_id = current_user.id` when creating PaymentBatch/DunningRecord
   - Set `updated_by_id = current_user.id` when updating them

4. **`app/services/banking/dunning_service.py`** + **`app/services/banking/payment_service.py`** - Service layer:
   - Pass `user_id` through to model creation/update calls
   - Set `created_by_id`/`updated_by_id` at service level

---

## Feature 3.2: API Pagination Standardization

### Problem
Pagination is inconsistent across endpoints:
- `documents.py`: Uses `limit`/`offset` (Pattern A)
- `entities.py`: Mix of `page`/`per_page` (Pattern B) and `page`/`page_size` (Pattern C)
- Some endpoints: `limit` only with no offset (Pattern D)

A `PaginationParams` class exists at `app/db/schemas.py:856-860` but is unused.

### Approach
Create a standard `Depends()` pagination utility and apply it to endpoints that use inconsistent patterns. Don't break existing APIs - add the standard pattern alongside for new code, and refactor only where it's clearly inconsistent.

### Files to Create

1. **`app/core/pagination.py`** - Standard pagination dependency:
   ```python
   class PaginatedResponse(BaseModel, Generic[T]):
       items: List[T]
       total: int
       page: int
       per_page: int
       total_pages: int

   def get_pagination(
       page: int = Query(1, ge=1, description="Seitennummer"),
       per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
   ) -> PaginationParams:
       ...
   ```

### Files to Modify

2. **`app/api/v1/entities.py`** - Standardize the 3 different pagination patterns:
   - Replace `page_size` with `per_page` where used (lines 170, 289)
   - Use `get_pagination` dependency

3. **Response format**: Ensure paginated endpoints return consistent metadata:
   ```json
   {
     "items": [...],
     "total": 150,
     "page": 1,
     "per_page": 20,
     "total_pages": 8
   }
   ```

**Note**: `documents.py` uses `limit`/`offset` which is a valid pattern for infinite scroll - this will NOT be changed (different use case).

---

## Feature 3.3: Error Code Consistency

### Current State
- `app/core/exceptions.py` already defines `AblageSystemException` with `error_code`, `message`, `user_message_de` (line 10-33)
- Subclasses: `NotFoundError` (E404), `ForbiddenError` (E403), `ValidationError` (E400) (lines 37-70)
- `app/api/v1/errors.py` has full error tracking system (lines 27-419)
- Most endpoints use raw `HTTPException` with inline German messages instead of the standard exception classes

### Approach
This is mostly already done. The improvement is to:
1. Add a few missing error code constants for common patterns
2. Register exception handlers in main.py to convert `AblageSystemException` to proper HTTP responses

### Files to Modify

1. **`app/core/exceptions.py`** - Add missing error codes:
   - `ConflictError` (E409) for duplicate resources
   - `RateLimitError` (E429) for rate limit exceeded
   - `ServiceUnavailableError` (E503) for backend service failures

2. **`app/main.py`** - Register exception handler:
   - Add `@app.exception_handler(AblageSystemException)` to convert custom exceptions to proper JSON responses with error_code field

---

## Implementation Strategy

### Single Agent (Backend-only, 3-8 files modified)
This is a contained C2-level task touching only backend files. One agent handles all three sub-features sequentially.

### Execution Order
1. Audit trail columns + migration (models.py + migration 219)
2. Set created_by_id/updated_by_id in API endpoints
3. Pagination utility + standardize entities.py
4. Error code additions + exception handler
5. Unit tests for pagination utility

### Files Summary

| Action | File | Feature |
|--------|------|---------|
| Modify | `app/db/models.py` | 3.1 Audit Trail |
| Create | `alembic/versions/219_add_audit_trail_fields.py` | 3.1 Audit Trail |
| Modify | `app/api/v1/banking/routes.py` | 3.1 Audit Trail |
| Modify | `app/services/banking/dunning_service.py` | 3.1 Audit Trail |
| Modify | `app/services/banking/payment_service.py` | 3.1 Audit Trail |
| Create | `app/core/pagination.py` | 3.2 Pagination |
| Modify | `app/api/v1/entities.py` | 3.2 Pagination |
| Modify | `app/core/exceptions.py` | 3.3 Error Codes |
| Modify | `app/main.py` | 3.3 Error Codes |

---

## Verification

### Audit Trail
- PaymentBatch and DunningRecord models have `created_by_id` and `updated_by_id` columns
- Migration 219 runs cleanly (upgrade + downgrade)
- Creating a payment batch or dunning record sets `created_by_id`
- Updating sets `updated_by_id`

### Pagination
- `app/core/pagination.py` exports `get_pagination` dependency and `PaginatedResponse`
- entities.py endpoints use consistent `page`/`per_page` parameters
- Response includes `total`, `page`, `per_page`, `total_pages`

### Error Codes
- `ConflictError`, `RateLimitError`, `ServiceUnavailableError` exist in exceptions.py
- Exception handler in main.py converts `AblageSystemException` to JSON with `error_code`
- Raising `NotFoundError("test", details={})` returns `{"error_code": "E404", ...}`

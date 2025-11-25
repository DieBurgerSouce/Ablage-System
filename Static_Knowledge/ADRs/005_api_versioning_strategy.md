# ADR-005: API Versioning Strategy

**Status**: Accepted
**Date**: 2025-11-22
**Deciders**: Backend Team, Product Team
**Consulted**: Frontend Team, DevOps

## Context and Problem Statement

As the Ablage-System API evolves, we need a versioning strategy that allows us to:
- Make backwards-incompatible changes without breaking existing clients
- Support multiple API versions simultaneously during migration periods
- Clearly communicate changes to API consumers
- Minimize maintenance burden of supporting multiple versions

## Decision Drivers

- **Client compatibility**: Existing integrations must continue working
- **Developer experience**: Clear, predictable versioning scheme
- **Maintenance cost**: Balance between flexibility and operational overhead
- **Migration path**: Smooth transition for clients upgrading versions
- **Documentation**: Easy to document and discover versions

## Considered Options

### Option 1: URL Path Versioning
```
/api/v1/documents
/api/v2/documents
```

### Option 2: Header-based Versioning
```
GET /api/documents
Accept: application/vnd.ablage.v1+json
```

### Option 3: Query Parameter Versioning
```
/api/documents?version=1
```

### Option 4: Subdomain Versioning
```
v1.api.ablage.company.de/documents
v2.api.ablage.company.de/documents
```

## Decision Outcome

**Chosen option**: **Option 1 - URL Path Versioning**

### Rationale

**Pros**:
- ✅ **Simplicity**: Most straightforward for clients to understand and use
- ✅ **Discoverability**: Version visible in URL, easy to test in browser
- ✅ **Routing**: Easy to implement in FastAPI with versioned routers
- ✅ **Documentation**: OpenAPI docs naturally separate by version
- ✅ **Caching**: CDNs and proxies can cache different versions separately
- ✅ **Industry standard**: Used by GitHub, Stripe, Twilio, etc.

**Cons**:
- ❌ Clutters URL namespace
- ❌ Requires maintaining separate route definitions

**Why not the others**:
- **Option 2 (Headers)**: Not discoverable, harder to test, requires header inspection
- **Option 3 (Query params)**: Clutters URLs, non-standard, caching issues
- **Option 4 (Subdomains)**: Complex DNS setup, SSL certificate management

## Implementation Details

### Version Format

Use simple integer versioning: `v1`, `v2`, `v3`, etc.

- **Major versions only**: Breaking changes warrant new version
- **Minor/patch changes**: Made within existing version (backwards compatible)

### URL Structure

```
https://ablage.company.de/api/v{version}/{resource}
```

**Examples**:
```
GET  /api/v1/documents
POST /api/v1/documents
GET  /api/v1/documents/{id}

GET  /api/v2/documents  # New version with different schema
```

### Version Lifecycle

```
Phase 1: Development
↓
Phase 2: Beta (v{N}-beta) - Limited release, may change
↓
Phase 3: Stable (v{N}) - Generally available, stable
↓
Phase 4: Deprecated - Announced end-of-life date
↓
Phase 5: Sunset - No longer available
```

**Timeline**:
- **Development**: Internal only, rapid iteration
- **Beta**: 1-2 months, feedback collection
- **Stable**: Minimum 12 months support
- **Deprecated**: 6 months notice before sunset
- **Sunset**: Version removed, returns 410 Gone

### FastAPI Implementation

```python
# app/api/v1/__init__.py
from fastapi import APIRouter

router_v1 = APIRouter(prefix="/api/v1", tags=["v1"])

@router_v1.get("/documents")
async def list_documents_v1():
    """V1: Returns documents with basic metadata."""
    return {"documents": [...]}

# app/api/v2/__init__.py
from fastapi import APIRouter

router_v2 = APIRouter(prefix="/api/v2", tags=["v2"])

@router_v2.get("/documents")
async def list_documents_v2():
    """V2: Returns documents with enhanced metadata and pagination."""
    return {
        "documents": [...],
        "pagination": {...},
        "metadata": {...}
    }

# app/main.py
from fastapi import FastAPI
from app.api.v1 import router_v1
from app.api.v2 import router_v2

app = FastAPI()
app.include_router(router_v1)
app.include_router(router_v2)
```

### Shared Code Organization

```
app/
├── api/
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── documents.py
│   │   ├── ocr.py
│   │   └── schemas.py  # V1-specific Pydantic models
│   ├── v2/
│   │   ├── __init__.py
│   │   ├── documents.py
│   │   ├── ocr.py
│   │   └── schemas.py  # V2-specific Pydantic models
│   └── dependencies.py  # Shared dependencies
├── services/
│   └── document_service.py  # Shared business logic
└── db/
    └── repositories.py  # Shared data access
```

**Principle**: Version-specific code in `api/vX/`, shared business logic in `services/`.

### Breaking Changes Definition

A change is **breaking** if it:
- Removes or renames a field in response
- Changes field data type
- Adds required request field
- Removes an endpoint
- Changes error response format
- Changes authentication mechanism

**Non-breaking** changes (can be added to existing version):
- Adding optional request fields
- Adding new response fields
- Adding new endpoints
- Adding new query parameters (optional)
- Improving error messages

### Deprecation Process

#### Step 1: Announce Deprecation (6 months before sunset)

**Methods**:
- API response header: `Sunset: Sat, 01 Aug 2025 23:59:59 GMT`
- Deprecation header: `Deprecation: @1735689599`
- Email notification to all API consumers
- Documentation update with migration guide

**Example Response Headers**:
```http
HTTP/1.1 200 OK
Sunset: Sat, 01 Aug 2025 23:59:59 GMT
Deprecation: @1735689599
Link: </api/v2/documents>; rel="successor-version"
Warning: 299 - "API version v1 is deprecated. Please migrate to v2."
```

#### Step 2: Migration Period (6 months)

- Both versions available
- Dual-write if needed (updates in both v1 and v2)
- Monitor v1 usage (expect decline)
- Provide migration tooling/scripts

**Migration Guide Template**:
```markdown
# Migrating from V1 to V2

## Breaking Changes

### 1. Document Response Schema

**V1**:
```json
{
  "id": "123",
  "name": "invoice.pdf",
  "date": "2025-01-22"
}
```

**V2**:
```json
{
  "id": "123",
  "filename": "invoice.pdf",  // Renamed from "name"
  "uploaded_at": "2025-01-22T10:30:00Z"  // ISO 8601 format
}
```

**Migration**: Update client code to use `filename` and `uploaded_at`.

### 2. Pagination

**V1**: No pagination (all results returned)
**V2**: Paginated results required

**Migration**: Add pagination parameters:
```
GET /api/v2/documents?page=1&page_size=20
```

## New Features in V2

- Enhanced filtering options
- Bulk operations support
- Webhook support
- Improved error messages
```

#### Step 3: Sunset (After 6 months)

- Remove v1 routers from application
- Return `410 Gone` with migration information

```python
@router_v1.get("/documents")
async def sunset_endpoint():
    """V1 has been sunset."""
    raise HTTPException(
        status_code=410,
        detail={
            "error": "API version v1 has been sunset",
            "sunset_date": "2025-08-01",
            "migration_guide": "https://docs.ablage.company.de/api/migration/v1-to-v2",
            "current_version": "v2",
            "current_endpoint": "/api/v2/documents"
        }
    )
```

### Version Discovery

#### API Root Endpoint

```python
@app.get("/api")
async def api_versions():
    """List all available API versions."""
    return {
        "versions": [
            {
                "version": "v1",
                "status": "deprecated",
                "sunset_date": "2025-08-01",
                "docs": "/api/v1/docs"
            },
            {
                "version": "v2",
                "status": "stable",
                "docs": "/api/v2/docs",
                "released": "2025-01-15"
            },
            {
                "version": "v3-beta",
                "status": "beta",
                "docs": "/api/v3-beta/docs",
                "released": "2025-11-01"
            }
        ],
        "latest_stable": "v2",
        "recommended": "v2"
    }
```

### Documentation Strategy

- **Separate OpenAPI docs per version**: `/api/v1/docs`, `/api/v2/docs`
- **Version comparison page**: Side-by-side diff of versions
- **Migration guides**: Detailed upgrade instructions
- **Changelog**: Track all changes between versions

### Monitoring & Metrics

Track per-version metrics:
```python
# Prometheus metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['version', 'endpoint', 'status']
)

# Example usage
api_requests_total.labels(version='v1', endpoint='/documents', status='200').inc()
```

**Key Metrics**:
- Requests per version (track v1 decline)
- Error rates per version
- Response times per version
- Unique clients per version

### Client Communication

**When releasing new version**:
1. Email all registered API consumers
2. Update documentation
3. Announce in changelog
4. Provide migration window (minimum 6 months)

**Email Template**:
```
Subject: New API Version Available: v2

Dear Ablage API Consumer,

We're excited to announce the release of API v2, which includes:
- Enhanced document metadata
- Improved pagination
- Webhook support
- Better error messages

Timeline:
- v2 available: January 15, 2025
- v1 deprecation: February 1, 2025
- v1 sunset: August 1, 2025 (6 months)

Migration Resources:
- Migration guide: https://docs.ablage.company.de/api/migration/v1-to-v2
- Changelog: https://docs.ablage.company.de/api/changelog
- Support: api-support@company.de

The v1 API will continue to work for 6 months. Please plan your migration accordingly.

Best regards,
Ablage Development Team
```

## Consequences

### Positive

- Clear, predictable versioning for clients
- Flexibility to make breaking changes
- Smooth migration path for upgrades
- Standard industry practice (familiar to developers)
- Easy to implement and maintain

### Negative

- Multiple codebases to maintain during transition periods
- Increased testing surface (test all supported versions)
- Documentation overhead (docs per version)
- Potential for version sprawl if not managed

### Mitigation Strategies

**To minimize negative consequences**:
1. **Limit supported versions**: Max 2 stable versions at once
2. **Enforce sunset timeline**: Strictly adhere to 6-month deprecation
3. **Share business logic**: Keep versioning in API layer only
4. **Automate testing**: Version matrix in CI/CD
5. **Monitor usage**: Track adoption of new versions

## Validation

**Success Criteria**:
- [ ] Zero breaking changes in stable versions without new version
- [ ] All version transitions completed within 6 months
- [ ] 95%+ of clients migrated before sunset
- [ ] Clear documentation for all versions
- [ ] Deprecation headers implemented

**Review Schedule**:
- After first version transition (v1 → v2)
- Annually to assess effectiveness

## Related Decisions

- ADR-001: Architecture Decisions (REST API choice)
- ADR-003: German Text Normalization (applies to all versions)

## References

- [Semantic Versioning](https://semver.org/)
- [API Versioning Best Practices (Microsoft)](https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design#versioning)
- [Stripe API Versioning](https://stripe.com/docs/api/versioning)
- [GitHub API Versioning](https://docs.github.com/en/rest/overview/api-versions)

## Appendix: Example Version Transition

### V1 → V2 Transition Timeline

```
2025-01-15: V2 released (stable)
2025-02-01: V1 deprecated (announce sunset)
2025-02 - 2025-07: Migration period
  - Weekly usage reports
  - Email reminders at 6mo, 3mo, 1mo, 2wk, 1wk
  - Support migration questions
2025-08-01: V1 sunset (return 410 Gone)
```

### Breaking Changes in V2

1. **Document Schema**: Renamed `name` → `filename`
2. **Pagination**: Added required pagination (page, page_size)
3. **Date Format**: Changed to ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)
4. **Error Format**: Standardized error response structure

### Non-Breaking Additions in V2

1. **Filtering**: Added `?status=`, `?uploaded_after=` query params
2. **Sorting**: Added `?sort_by=`, `?sort_order=` query params
3. **Webhooks**: New `/webhooks` endpoint
4. **Bulk Operations**: New `/documents/bulk` endpoint

---

**Last Updated**: 2025-11-22
**Next Review**: 2026-01-15

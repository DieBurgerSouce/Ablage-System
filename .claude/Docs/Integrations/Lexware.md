# Lexware Integration

> Extrahiert aus `.claude/CLAUDE.md` - AUTO-MANAGED Sektion
> Letzte Aktualisierung: 2026-01-11

**Status**: ✅ Production-Ready (commit 5f9b5e55)
**Migration**: 089_add_lexware_fields, 090_merge_lexware_streckengeschaeft

---

## Overview

Lexware Integration ermöglicht automatischen Import und Verknüpfung von Kunden-/Lieferantendaten aus Lexware-Buchhaltungssoftware-Exporten.

---

## Core Services

| Service | File | Purpose |
|---------|------|---------|
| **LexwareImportService** | `lexware_import_service.py` | Excel-Import, Konflikt-Erkennung |
| **EntitySearchService** | `entity_search_service.py` | Multi-Strategie-Suche (Kundennr, IBAN, VAT-ID) |
| **DocumentEntityLinkerService** | `document_entity_linker_service.py` | Auto-Linking nach OCR |

---

## Database Schema Changes

**BusinessEntity Model** (Migration 089):
```python
lexware_ids: JSONB  # {"folie": {"kd_nr": "12345", "matchcode": "MUELLER"}, ...}
company_presence: JSONB  # ["folie", "messer"]
primary_customer_number: String(50)  # Display number
primary_supplier_number: String(50)  # Display number
```

**Indexes**:
- `ix_business_entities_primary_customer_number` (B-tree)
- `ix_business_entities_primary_supplier_number` (B-tree)
- `ix_business_entities_lexware_ids_gin` (GIN for JSONB)
- `ix_business_entities_company_presence_gin` (GIN for array)

---

## Import Workflow

```
1. User uploads Lexware Excel (150 customers)
   ↓
2. LexwareImportService processes file
   ↓
3. Conflict detection:
   - Critical: Different addresses/phone → Skip (default)
   - Harmless: Name variants (GmbH vs GmbH & Co) → Auto-merge
   - Duplicates: Same entity in both lists → Merge with company_presence
   ↓
4. Import: 145 customers (5 skipped due to conflicts)
   ↓
5. Auto-trigger: link_all_documents_task (Celery)
   ↓
6. DocumentEntityLinkerService processes all documents
   ↓
7. Extract patterns: Customer numbers, IBANs, VAT-IDs, company names
   ↓
8. Match with confidence: 78 linked (>75%), 12 flagged for review
```

---

## API Endpoints

### Lexware Import (`/api/v1/lexware`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/lexware/import/customers` | POST | Import customers from Excel |
| `/api/v1/lexware/import/suppliers` | POST | Import suppliers from Excel |
| `/api/v1/lexware/link-documents` | POST | Trigger entity linking |
| `/api/v1/lexware/statistics` | GET | Import/linking stats |
| `/api/v1/lexware/search` | POST | Smart entity search |

### Entity Management (`/api/v1/entities`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entities` | GET | List all entities with filters |
| `/api/v1/entities/{id}` | GET | Get entity details |
| `/api/v1/entities/customers` | GET | List customers (frontend format, paginated) |
| `/api/v1/entities/suppliers` | GET | List suppliers (frontend format, paginated, sortable) |
| `/api/v1/entities/{id}/folders` | GET | Get entity folders (folie/messer) |

### Pagination Parameters

- `page` (int, default: 1) - Seitennummer
- `page_size` (int, default: 50, max: 200) - Einträge pro Seite
- `search` (str, optional) - Suche in Name/Matchcode/Kundennummer
- `sort_by` (str, default: "name") - Sortierfeld (name, created_at, document_count)
- `sort_order` (str, default: "asc") - Sortierrichtung (asc, desc)
- `is_active` (bool, optional) - Nach Aktivstatus filtern

---

## Celery Tasks

| Task | Trigger | Purpose |
|------|---------|---------|
| `entity_linking.link_all_documents` | After Lexware import | Batch-link all unlinked docs |
| `entity_linking.link_single_document` | After OCR completion | Link single document |
| `entity_linking.post_lexware_import` | After import success | Orchestrate linking + stats |

---

## Document Entity Linking

### Matching Strategies (Priority Order)

| Strategy | Confidence | Pattern Example |
|----------|------------|-----------------|
| Exact customer number | 99% | `Kd-Nr: 12345` |
| Exact matchcode | 95% | `MUELLER` in header |
| IBAN match | 90% | `DE89370400440532013000` |
| VAT-ID match | 90% | `DE123456789` |
| Fuzzy company name | 80% | `Mueller GmbH` vs `Müller GmbH` (>85% similarity) |
| Address match | 75% | PLZ + street name |

### Pattern Extraction (from OCR text)

```python
# Customer number patterns
r"(?:Kd\.?-?Nr\.?|Kundennummer)[\s:]*(\d{3,8})"

# IBAN pattern
r"\b([A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){3,7}\d{1,4})\b"

# German VAT-ID pattern
r"\b(DE(?:\s*\d){9})\b"
```

---

## Conflict Resolution

**Similarity Thresholds**:
- `CRITICAL_SIMILARITY_THRESHOLD = 0.5` → Below = critical conflict (skip)
- `HARMLESS_SIMILARITY_THRESHOLD = 0.7` → Above = harmless variant (auto-merge)

**Conflict Types**:
1. **Critical**: Different addresses, phone, email → Skip by default
2. **Harmless**: Name variants (GmbH vs GmbH & Co) → Auto-merge
3. **Duplicates**: Same entity in both lists → Merge with company_presence tracking

---

## Search Capabilities

**EntitySearchService Methods**:
- `find_by_customer_number(kd_nr, company)` → Exact match
- `find_by_supplier_number(lief_nr, company)` → Exact match
- `find_by_matchcode(matchcode, fuzzy)` → Fuzzy matching
- `find_by_iban(iban)` → Normalized IBAN search
- `find_by_vat_id(vat_id)` → VAT-ID search
- `smart_search(query)` → Multi-strategy search

---

## Security & PII Protection

| Rule | Implementation |
|------|----------------|
| **No PII in logs** | NEVER log customer numbers, IBANs, VAT-IDs |
| **Excel validation** | Strict structure validation before import |
| **Rate limiting** | Max 10 imports/hour per user |
| **Admin only** | Import operations require admin role |
| **Conflict review** | Critical conflicts require manual approval |

---

## Testing

**Unit Test Coverage**:
- `tests/unit/services/test_lexware_import_service.py` (50+ tests)
- `tests/unit/services/test_entity_search_service.py` (40+ tests)
- `tests/unit/services/test_document_entity_linker_service.py` (35+ tests)

**Test Categories**:
- Helper functions (normalize_text, calculate_similarity, is_placeholder)
- Conflict detection and resolution
- Pattern extraction from German business documents
- Fuzzy matching with German umlauts (ä, ö, ü, ß)
- IBAN/VAT-ID validation and extraction
- Multi-company data handling

---

## Frontend Integration

### Display Format

- **Customers**: `"12345_Mueller"` (Kundennummer_Matchcode)
  - Backend ALWAYS constructs displayName from primary_customer_number + matchcode
  - Frontend filters fullName: Only show if real company name
- **Suppliers**: `"Agrimpex"` (name only, no number)

### API Response Types

```typescript
interface CustomerForFrontend {
  id: string;
  displayName: string;        // "12345_Mueller"
  fullName: string;           // "Müller GmbH & Co. KG" OR placeholder
  isActive: boolean;
  companyPresence: string[];  // ["folie", "messer"]
  folderStats: Record<string, FolderStats>;
}

interface EntityFolder {
  id: string;                 // "folie" or "messer"
  name: string;               // "Folie" or "Spargelmesser"
  documentCounts: Record<string, number>;
  openInvoices: number;
  lastActivity: string | null;
}
```

### DisplayName Construction (Backend)

```python
# NEVER trust entity.display_name - ALWAYS construct from customer number + matchcode
display_name = f"{primary_customer_number}_{matchcode}"
# Example: "10006_Peter", "12345_Mueller"
```

### FullName Validation (Frontend)

```typescript
function isRealCompanyName(fullName: string): boolean {
  if (!fullName || fullName.trim() === '') return false
  const startsWithNumber = /^\d/.test(fullName)
  const containsCustomerNumber = /^\d{3,8}_/.test(fullName)
  return !startsWithNumber && !containsCustomerNumber
}
```

---

## Integration Points

| Module | Integration |
|--------|-------------|
| Document Service | OCR completion → triggers entity linking |
| Validation Services | Uses EntitySearchService for duplicate checks |
| Event Bus | Emits `entity.linked` events for orchestration |
| Frontend Ablage | Customer/supplier lists, folder navigation, real-time stats |

---

## Configuration

```python
MIN_LINK_CONFIDENCE = 0.75  # Minimum for automatic linking
BATCH_SIZE = 100  # Documents per linking batch
DEFAULT_SIMILARITY_THRESHOLD = 0.7  # Fuzzy name matching
```

---

## Known Issues & Limitations

- ❌ Excel must follow Lexware export format (specific column names)
- ❌ Only supports German company formats (GmbH, AG, KG, etc.)
- ⚠️ Fuzzy matching may need manual review for edge cases
- ⚠️ Multi-company entities require careful conflict handling

---

## Critical Bug Fixes (2026-01-10)

**BUG #1: FastAPI Route Ordering Issue** (`app/api/v1/entities.py`)
- **Problem**: Static routes `/customers` and `/suppliers` defined AFTER dynamic `/{entity_id}`
- **Fix**: Moved static routes BEFORE `/{entity_id}` route
- **Commit**: 665ca1cc

**BUG #2: Missing Cookie Credentials** (`ablage-api.ts`)
- **Problem**: Entity API fetch calls not sending httpOnly session cookies
- **Fix**: Added `credentials: "include"` to all fetch calls
- **Commit**: 25542547

---

## Future Enhancements

- [ ] Support for Austrian/Swiss company formats
- [ ] ML-based entity matching (beyond fuzzy string matching)
- [ ] Automatic conflict resolution with user preferences
- [ ] Real-time Lexware API integration (instead of Excel)
- [ ] Entity deduplication across companies

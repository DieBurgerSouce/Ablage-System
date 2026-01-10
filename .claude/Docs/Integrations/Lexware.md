# Lexware Integration (Januar 2026)

## Overview

The Lexware Integration module provides automated import and linking of customer/supplier data from Lexware accounting software exports.

## Core Services

### LexwareImportService
**File**: `app/services/lexware_import_service.py`

- Imports customer/supplier data from Excel exports
- Supports two companies: "Folie" and "Messer"
- Automatic conflict detection and resolution
- Name variant recognition (e.g., "Mueller GmbH" vs "Mueller GmbH & Co")
- Duplicate detection within import lists

### EntitySearchService
**File**: `app/services/entity_search_service.py`

Search capabilities:
- Customer number (primary_customer_number + JSONB lexware_ids)
- Supplier number (primary_supplier_number + JSONB lexware_ids)
- Matchcode (exact match)
- Fuzzy name search (configurable threshold, default 0.7)
- IBAN search (German bank accounts)
- VAT-ID search (German USt-IdNr format: DE + 9 digits)
- Pattern-based searches (LIKE queries)

### DocumentEntityLinkerService
**File**: `app/services/document_entity_linker_service.py`

- Automatically links documents to BusinessEntities after OCR completion
- Extracts patterns from OCR text (customer numbers, IBANs, VAT-IDs, company names)
- Multi-strategy matching with confidence scores
- Minimum confidence threshold: 75% for automatic linking

## Database Schema

Migration `089_add_lexware_fields.py` adds to BusinessEntity:

```python
lexware_ids: JSONB  # {"folie": {"kd_nr": "12345", "matchcode": "MUELLER"}, "messer": {...}}
company_presence: JSONB  # ["folie", "messer"] or ["folie"]
primary_customer_number: String(50)
primary_supplier_number: String(50)

# Indexes
- ix_business_entities_primary_customer_number
- ix_business_entities_primary_supplier_number
- ix_business_entities_lexware_ids_gin (GIN index for JSONB)
- ix_business_entities_company_presence_gin (GIN index for array)
```

## Import Conflict Resolution

### Conflict Types

| Type | Behavior |
|------|----------|
| Critical Conflicts | Different addresses, phone, email -> Skip by default |
| Harmless Conflicts | Name variants, formatting -> Auto-merge |
| Duplicates | Same entity in both lists -> Merge with company_presence |

### Similarity Thresholds

```python
CRITICAL_SIMILARITY_THRESHOLD = 0.5  # Below = critical conflict
HARMLESS_SIMILARITY_THRESHOLD = 0.7  # Above = harmless (auto-merge)
```

## Document Entity Linking

### Matching Strategies (Priority Order)

| Strategy | Confidence | Description |
|----------|------------|-------------|
| Exact customer number | 99% | Customer number in OCR text |
| Exact matchcode | 95% | Matchcode in OCR text |
| IBAN match | 90% | IBAN matches entity |
| VAT-ID match | 90% | VAT-ID matches entity |
| Fuzzy company name | 80% | Name similarity >85% |
| Address match | 75% | PLZ + street match |

### Pattern Extraction

```python
# Customer number patterns
r"(?:Kd\.?-?Nr\.?|Kundennummer|Kunden-?Nr\.?)[\s:]*(\d{3,8})"

# Supplier number patterns
r"(?:Lief\.?-?Nr\.?|Lieferantennummer)[\s:]*(\d{3,8})"

# IBAN pattern
r"\b([A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){3,7}\d{1,4})\b"

# VAT-ID pattern (German)
r"\b(DE(?:\s*\d){9})\b"
```

## API Endpoints

```python
POST /api/v1/lexware/import/customers   # Import customers
POST /api/v1/lexware/import/suppliers   # Import suppliers
POST /api/v1/lexware/link-documents     # Trigger entity linking
GET  /api/v1/lexware/statistics         # Linking statistics
POST /api/v1/lexware/search             # Entity search
```

### Request Models

```python
LexwareImportRequest:
  company: str          # "folie" or "messer"
  skip_conflicts: bool  # Default: True
  dry_run: bool         # Default: False

EntityLinkingRequest:
  min_confidence: float  # Default: 0.75
  only_unlinked: bool    # Default: True
  batch_size: int        # Default: 100
  async_mode: bool       # Default: True
```

## Celery Tasks

```python
@celery_app.task(name="entity_linking.link_all_documents")
def link_all_documents_task(min_confidence=0.75, batch_size=100)
  """Batch-link all documents with BusinessEntities."""

@celery_app.task(name="entity_linking.link_single_document")
def link_single_document_task(document_id: str, min_confidence=0.75)
  """Link single document after OCR completion."""
```

### Automatic Triggering
- After Lexware import: `link_all_documents_task` auto-triggered
- After OCR completion: `link_single_document_task` in processing pipeline

## Workflow Example

```
1. User uploads Lexware customer Excel (150 customers)
2. LexwareImportService processes file
3. Detects 5 conflicts (3 critical, 2 harmless)
4. Merges 2 harmless variants, skips 3 critical
5. Imports 145 customers successfully
6. Triggers link_all_documents_task
7. Links 78 documents automatically (>75% confidence)
8. Flags 12 documents for manual review
```

## Security Considerations

- **PII Protection**: NEVER log customer numbers, IBANs, or VAT-IDs
- **Input Validation**: Excel files validated for structure
- **Rate Limiting**: 10 imports/hour per user
- **Access Control**: Import requires admin role

## Testing

```python
# Unit Tests
tests/unit/services/test_lexware_import_service.py
tests/unit/services/test_entity_search_service.py
tests/unit/services/test_document_entity_linker_service.py

# Coverage areas:
- Import conflict detection/resolution
- Pattern extraction from German documents
- Fuzzy matching with umlauts
- IBAN/VAT-ID validation
- Multi-company data handling
```

## Integration Points

| Service | Integration |
|---------|-------------|
| Document Service | OCR completion triggers linking |
| Validation Services | Uses EntitySearchService for duplicates |
| Event Bus | Emits `entity.linked` events |
| Frontend | Import workflow UI components |

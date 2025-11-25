# SOP-003: Adding New Document Template
## Create, Test, and Deploy Custom Extraction Templates

**Status**: Active
**Audience**: Developers, Data Engineers
**Estimated Time**: 30-45 minutes per template
**Prerequisites**: Understanding of regex, German document formats

---

## Overview

This SOP guides you through creating a new document template for structured data extraction. Templates define how to extract fields from specific document types (invoices, contracts, forms, etc.).

**Use Cases**:
- New document type (e.g., delivery notes, tax documents)
- Vendor-specific layout variation
- Custom form templates
- Regional document formats

---

## Table of Contents

1. [Prerequisites](#step-1-prerequisites)
2. [Analyze Document Type](#step-2-analyze-document-type)
3. [Create Template YAML](#step-3-create-template-yaml)
4. [Define Extraction Patterns](#step-4-define-extraction-patterns)
5. [Add Validation Rules](#step-5-add-validation-rules)
6. [Test Template](#step-6-test-template)
7. [Deploy Template](#step-7-deploy-template)
8. [Monitor Performance](#step-8-monitor-performance)

---

## Step 1: Prerequisites

### 1.1 Gather Sample Documents
Collect 5-10 examples of the document type:
```bash
mkdir -p test_samples/new_template/
# Place sample PDFs/images in this directory
```

### 1.2 Convert to OCR Text
```bash
# Process samples with OCR
python3 << EOF
from app.services.ocr_service import OCRService
import os

ocr = OCRService()

for filename in os.listdir('test_samples/new_template/'):
    if filename.endswith(('.pdf', '.png', '.jpg')):
        result = await ocr.process(
            document_path=f'test_samples/new_template/{filename}',
            backend='got_ocr'
        )

        # Save OCR text
        with open(f'test_samples/new_template/{filename}.txt', 'w') as f:
            f.write(result.text)

print("OCR processing complete!")
EOF
```

### 1.3 Identify Common Fields
Review OCR text files and identify:
- **Required fields**: Must be present for valid document
- **Optional fields**: Nice to have but not required
- **Field patterns**: How each field appears in text

---

## Step 2: Analyze Document Type

### 2.1 Document Classification
Determine how to identify this document type:

**Keywords** (appear in most documents):
- Example: ["Lieferschein", "Lieferung", "Artikel"]

**Layout characteristics**:
- Tables present? Yes/No
- Multi-column? Yes/No
- Handwritten sections? Yes/No

### 2.2 Map Required Fields
Create a field mapping table:

| Field Name | Description | Example Value | Format |
|------------|-------------|---------------|--------|
| lieferschein_nr | Delivery note number | LS-2024-001 | [A-Z]{2}-\d{4}-\d{3} |
| lieferdatum | Delivery date | 31.12.2024 | DD.MM.YYYY |
| lieferant | Supplier name | Müller GmbH | Company name + legal form |
| positionen | Line items | [{"artikel": "...", "menge": 5}] | Array of objects |

---

## Step 3: Create Template YAML

### 3.1 Create Template File
```bash
cd Static_Knowledge/Templates/
touch lieferschein_template.yaml
```

### 3.2 Template Structure
```yaml
# lieferschein_template.yaml
template_id: "lieferschein"
description: "German delivery note (Lieferschein)"
version: "1.0.0"
created: "2025-01-22"
author: "Your Name"

# Document type identification
identification:
  keywords:
    - "Lieferschein"
    - "Lieferung"
    - "Artikel"
  min_keyword_count: 2  # At least 2 keywords must be present
  confidence_threshold: 0.75

# Required fields (document invalid if missing)
required_fields:
  lieferschein_nr:
    description: "Delivery note number"
    pattern: 'Lieferschein(?:nummer|nr\.?)?\s*:?\s*([A-Z]{2}-\d{4}-\d{3})'
    examples:
      - "Lieferscheinnummer: LS-2024-001"
      - "Lieferschein-Nr. LS-2024-001"
    validation:
      min_length: 5
      max_length: 20
      format: "^[A-Z]{2}-\\d{4}-\\d{3}$"

  lieferdatum:
    description: "Delivery date (DD.MM.YYYY)"
    pattern: '(?:Liefer)?datum\s*:?\s*(\d{1,2}\.\d{1,2}\.\d{4})'
    examples:
      - "Lieferdatum: 31.12.2024"
      - "Datum 31.12.2024"
    validation:
      format: "DD.MM.YYYY"
      not_future: true  # Can't deliver in future
      max_age_days: 365  # Delivery within last year

  lieferant:
    description: "Supplier company name"
    pattern: '(?:Lieferant|Von)\s*:?\s*([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜa-zäöüß\-&]+)*\s+(?:GmbH|AG|KG))'
    examples:
      - "Lieferant: Müller GmbH"
      - "Von: Bäcker & Partner AG"
    validation:
      must_contain_legal_form: true

  empfaenger:
    description: "Recipient company name"
    pattern: '(?:Empfänger|An)\s*:?\s*([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜa-zäöüß\-&]+)*\s+(?:GmbH|AG|KG))'
    examples:
      - "Empfänger: Schulze KG"
    validation:
      must_contain_legal_form: true

# Optional fields
optional_fields:
  bestellnummer:
    description: "Order number reference"
    pattern: 'Bestellung(?:snummer|nr\.?)?\s*:?\s*([A-Z0-9-/]+)'
    examples:
      - "Bestellnummer: B-2024-050"

  lieferadresse:
    description: "Delivery address"
    pattern: '(?:Lieferadresse|Anschrift)\s*:?\s*(.+?)(?=\n\n|\n[A-Z]|$)'
    multiline: true

# Business rules and validation
business_rules:
  - name: "required_fields_complete"
    rule: "All required fields must be extracted"
    severity: "critical"

  - name: "date_not_future"
    rule: "lieferdatum <= today"
    severity: "high"

  - name: "supplier_not_recipient"
    rule: "lieferant != empfaenger"
    severity: "medium"

# Post-extraction processing
post_processing:
  normalize_company_names: true
  extract_line_items: true  # Parse table of delivered items
  calculate_total_quantity: true
```

---

## Step 4: Define Extraction Patterns

### 4.1 Regex Pattern Development
Test patterns interactively:

```python
import re

# Load sample OCR text
with open('test_samples/new_template/sample1.txt') as f:
    text = f.read()

# Test pattern
pattern = r'Lieferschein(?:nummer|nr\.?)?\s*:?\s*([A-Z]{2}-\d{4}-\d{3})'
matches = re.findall(pattern, text)

print(f"Matches: {matches}")
# Adjust pattern until all samples work
```

### 4.2 Pattern Best Practices

**DO**:
- ✅ Make patterns flexible (`(?:nummer|nr\.?)?` matches variations)
- ✅ Use non-capturing groups `(?:...)` for optional parts
- ✅ Test against all sample documents
- ✅ Include examples in template

**DON'T**:
- ❌ Over-specify (too strict patterns fail on variations)
- ❌ Use greedy quantifiers without limits (`.+` can match too much)
- ❌ Assume specific spacing/formatting
- ❌ Forget to escape special characters (`\.` for literal dot)

### 4.3 Handle German-Specific Patterns
```yaml
# Dates with month names
datum_with_month:
  pattern: '(\d{1,2})\.\s*(Januar|Februar|März|...|Dezember)\s*(\d{4})'

# Currency amounts
betrag:
  pattern: '(\d{1,3}(?:\.\d{3})*,\d{2})\s*€?'

# Company names with legal forms
firma:
  pattern: '([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜa-zäöüß\-&]+)*\s+(?:GmbH|AG|KG|GbR|UG))'
```

---

## Step 5: Add Validation Rules

### 5.1 Field-Level Validation
Define constraints for each field:

```yaml
lieferdatum:
  validation:
    format: "DD.MM.YYYY"
    not_future: true
    max_age_days: 365
    custom_check: |
      # Python code to validate
      from datetime import datetime
      date = datetime.strptime(value, '%d.%m.%Y')
      if date.weekday() == 6:  # Sunday
          logger.warning("delivery_on_sunday", date=value)
```

### 5.2 Cross-Field Validation
```yaml
business_rules:
  - name: "dates_logical_order"
    rule: "bestelldatum <= lieferdatum"
    error_message: "Lieferdatum kann nicht vor Bestelldatum sein"

  - name: "supplier_not_recipient"
    rule: "lieferant != empfaenger"
    error_message: "Lieferant und Empfänger müssen unterschiedlich sein"
```

### 5.3 Math Validation (for tables)
```yaml
positionen_validation:
  rule: "sum(position.menge for position in positionen) == gesamtmenge"
  tolerance: 0
```

---

## Step 6: Test Template

### 6.1 Create Test Cases
```python
# tests/test_lieferschein_template.py
import pytest
from app.utils.template_extractor import TemplateExtractor

@pytest.fixture
def extractor():
    return TemplateExtractor()

@pytest.mark.parametrize("sample_file,expected_fields", [
    ("sample1.txt", {
        "lieferschein_nr": "LS-2024-001",
        "lieferdatum": "31.12.2024",
        "lieferant": "Müller GmbH"
    }),
    ("sample2.txt", {
        "lieferschein_nr": "LS-2024-002",
        "lieferdatum": "15.01.2025"
    }),
])
def test_lieferschein_extraction(extractor, sample_file, expected_fields):
    """Test extraction accuracy on sample documents."""
    with open(f'test_samples/new_template/{sample_file}') as f:
        text = f.read()

    result = extractor.extract(text, template="lieferschein")

    # Check all expected fields extracted
    for field, expected_value in expected_fields.items():
        assert field in result['fields']
        assert result['fields'][field]['value'] == expected_value

    # Check overall confidence
    assert result['overall_confidence'] > 0.85
```

### 6.2 Run Tests
```bash
pytest tests/test_lieferschein_template.py -v

# Expected: All tests passing
# If failures, adjust patterns in template YAML
```

### 6.3 Test with API
```bash
# Start server
python app/main.py &

# Upload test document
curl -X POST "http://localhost:8000/api/v1/documents/" \
  -F "file=@test_samples/new_template/sample1.pdf"

# Get document ID from response
DOC_ID="doc_abc123"

# Extract with new template
curl -X POST "http://localhost:8000/api/v1/templates/extract/${DOC_ID}" \
  -H "Content-Type: application/json" \
  -d '{"template_id": "lieferschein"}'

# Verify extraction result
```

---

## Step 7: Deploy Template

### 7.1 Register Template
Add to template registry:

```yaml
# app/config/templates.yaml
templates:
  - template_id: "rechnung"
    file: "Static_Knowledge/Templates/rechnungen_template.yaml"
    priority: 1

  - template_id: "lieferschein"  # NEW
    file: "Static_Knowledge/Templates/lieferschein_template.yaml"
    priority: 2

  - template_id: "vertrag"
    file: "Static_Knowledge/Templates/vertrag_template.yaml"
    priority: 3
```

### 7.2 Update Documentation
```markdown
# Update CLAUDE.md
## Supported Document Templates

1. **Rechnung (Invoice)** - §14 UStG compliant
2. **Lieferschein (Delivery Note)** - NEW! (v1.0.0, 2025-01-22)
3. **Vertrag (Contract)** - Coming soon

## Lieferschein Template
- **Required fields**: 4 (lieferschein_nr, lieferdatum, lieferant, empfaenger)
- **Optional fields**: 2 (bestellnummer, lieferadresse)
- **Accuracy**: 96% (tested on 20 samples)
- **File**: [lieferschein_template.yaml](Static_Knowledge/Templates/lieferschein_template.yaml)
```

### 7.3 Restart Services
```bash
# If using Docker
docker-compose restart backend worker

# If running locally
sudo systemctl restart ablage-backend
sudo systemctl restart ablage-worker
```

---

## Step 8: Monitor Performance

### 8.1 Track Metrics
Monitor template usage and accuracy:

```python
# In app/services/template_extraction.py
logger.info(
    "template_extraction_complete",
    template_id="lieferschein",
    overall_confidence=result['overall_confidence'],
    required_fields_extracted=len(result['fields']),
    processing_time_ms=processing_time
)
```

### 8.2 Weekly Review
Check template performance:
```sql
-- Query extraction logs
SELECT
  template_id,
  AVG(overall_confidence) as avg_confidence,
  COUNT(*) as extraction_count,
  SUM(CASE WHEN validation_passed THEN 1 ELSE 0 END) as success_count
FROM extraction_logs
WHERE template_id = 'lieferschein'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY template_id;
```

### 8.3 Iterate and Improve
Based on failures:
1. Collect failed extractions
2. Analyze patterns (which fields fail most?)
3. Update regex patterns
4. Increase test coverage
5. Redeploy updated template

---

## Troubleshooting

### Issue 1: Pattern matches too much
**Symptom**: Extracts wrong text or multiple values

**Solution**:
```yaml
# Add more specific context
# Before:
pattern: '(\d{1,2}\.\d{1,2}\.\d{4})'  # Matches any date

# After:
pattern: 'Lieferdatum\s*:?\s*(\d{1,2}\.\d{1,2}\.\d{4})'  # Specific context
```

### Issue 2: Pattern doesn't match variations
**Symptom**: Works on some samples, fails on others

**Solution**:
```yaml
# Make pattern more flexible
# Before:
pattern: 'Lieferscheinnummer:\s*([A-Z0-9-]+)'  # Requires colon + space

# After:
pattern: 'Lieferschein(?:nummer|nr\.?)?\s*:?\s*([A-Z0-9-]+)'  # Optional variations
```

### Issue 3: Low extraction confidence
**Symptom**: `overall_confidence < 0.85`

**Solution**:
1. Check OCR quality (poor OCR → low confidence)
2. Add more contextual keywords to patterns
3. Increase fuzzy matching tolerance for business terms

---

## Template Maintenance Checklist

### After Creation
- [ ] Template YAML created and validated
- [ ] At least 5 test cases with sample documents
- [ ] All required fields have extraction patterns
- [ ] Validation rules defined
- [ ] Tests passing (`pytest`)
- [ ] Template registered in `templates.yaml`
- [ ] Documentation updated (CLAUDE.md)
- [ ] Deployed to production

### Monthly Review
- [ ] Check extraction success rate (target: > 95%)
- [ ] Review failed extractions
- [ ] Update patterns if needed
- [ ] Add new test cases from production data

---

## References

- [Static_Knowledge/Templates/rechnungen_template.json](../Templates/rechnungen_template.json) - Example invoice template
- [Static_Knowledge/Skills/template_extraction_skill.yaml](../Skills/template_extraction_skill.yaml) - Extraction patterns
- [ADR-004: Template Extraction Strategy](../ADRs/004_template_extraction_strategy.md) - Design decisions
- [app/utils/template_extractor.py](../../app/utils/template_extractor.py) - Implementation
- **Regex Tutorial**: https://regex101.com/ (interactive testing)

---

**Last Updated**: 2025-01-22
**Next Review**: 2025-04-22
**SOP Owner**: Data Engineering Team

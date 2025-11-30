# German Test Documents for OCR Validation

Generated: 2025-11-30 00:56:18

## Summary

| Category | Count | Has Umlauts | Has Tables |
|----------|-------|-------------|------------|
| invoices | 6 | Yes | No |
| fraktur | 6 | Yes | No |
| tables | 6 | Yes | Yes |
| contracts | 6 | Yes | No |
| forms | 3 | Yes | No |
| handwritten | 3 | Yes | No |
| mixed | 3 | Yes | Yes |

## Total: 33 documents

## Categories

### Invoices
German invoices with IBAN, VAT ID, dates, and currency amounts.

### Fraktur
Historical German text in Fraktur style (simulated).

### Tables
Documents containing structured table data.

### Contracts
Formal German contract documents.

### Forms
Government-style form documents.

### Handwritten
Simulated handwritten German text.

### Mixed
Documents combining multiple element types.

## Ground Truth Format

Each document has a corresponding JSON file with ground truth:

```json
{
  "filename": "invoice_001.png",
  "category": "invoices",
  "source": "synthetic",
  "expected_text": "...",
  "expected_entities": {
    "iban": ["DE89..."],
    "date": ["22.11.2024"]
  },
  "has_umlauts": true,
  "has_tables": false,
  "language": "de",
  "license": "CC0"
}
```

## License

All documents are synthetic and licensed under CC0 (Public Domain).

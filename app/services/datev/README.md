# DATEV Export Service

DATEV-konformer Export fuer deutsche Buchhaltungssoftware.

## Uebersicht

Der DATEV-Export ermoeglicht:
- Buchungsexport im DATEV 700 Format
- Automatische Steuerschluessel-Zuordnung
- Kreditorenkonten-Mapping
- Batch-Export mit Fehlerbehandlung

## Format-Spezifikation

### DATEV 700 CSV Format

| Eigenschaft | Wert |
|-------------|------|
| Encoding | CP1252 (Windows Latin-1) |
| Delimiter | Semikolon (;) |
| Dezimaltrennzeichen | Komma (,) |
| Datumsformat | DDMM (ohne Jahr) |
| Zeilenende | CRLF (\r\n) |
| Header-Felder | 32 |
| Daten-Felder | 116 |

### Steuerschluessel (BU-Schluessel)

| Szenario | Steuersatz | BU (Eingang) | BU (Ausgang) |
|----------|------------|--------------|--------------|
| Standard 19% | 19% | 9 | 3 |
| Ermaessigt 7% | 7% | 8 | 2 |
| EU-Innengem. 19% | 19% | 94 | - |
| EU-Innengem. 7% | 7% | 93 | - |
| Reverse Charge 19% | 19% | 91 | - |
| Reverse Charge 7% | 7% | 92 | - |
| Drittland | 0% | 0 | 0 |
| IG-Lieferung | 0% | - | 10 |

## Verwendung

### Basis-Export

```python
from app.services.datev.export_service import DatevExportService

service = DatevExportService()
result = await service.export_documents(
    document_ids=["doc1", "doc2", "doc3"],
    export_type="buchungen",
    date_from=date(2024, 1, 1),
    date_to=date(2024, 12, 31)
)

# result.csv_content = bytes in CP1252
# result.filename = "EXTF_Buchungen_20241201_20241231.csv"
```

### Kreditoren-Mapping

```python
service = DatevExportService(
    vendor_mapping={
        "USt-IdNr.": {"DE123456789": "70001"},  # Nach USt-IdNr
        "IBAN": {"DE89370400440532013000": "70002"},  # Nach IBAN
        "Name": {"Lieferant GmbH": "70003"},  # Nach Name (case-insensitive)
    },
    default_creditor_account="70000"
)
```

### Batch-Export mit Fehlerbehandlung

```python
result = await service.export_batch(
    document_ids=document_ids,
    on_error="skip",  # oder "fail"
    batch_size=100
)

if result.errors:
    for error in result.errors:
        logger.warning(f"Dokument {error['doc_id']}: {error['message']}")
```

## API Endpoints

```
POST /api/v1/datev/export/buchungen
POST /api/v1/datev/export/documents
GET  /api/v1/datev/export/{export_id}/download
GET  /api/v1/datev/export/{export_id}/status
```

### Request Body

```json
{
    "document_ids": ["uuid1", "uuid2"],
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "export_type": "buchungen",
    "include_attachments": false
}
```

### Response

```json
{
    "export_id": "exp_123",
    "status": "completed",
    "document_count": 150,
    "error_count": 2,
    "download_url": "/api/v1/datev/export/exp_123/download"
}
```

## Validierung

Der Export validiert:
- Rechnungsnummer max. 36 Zeichen (wird abgeschnitten)
- Betrag wird als positiver Wert exportiert (Vorzeichen in Buchungstyp)
- Umlaute werden in CP1252 konvertiert
- Sonderzeichen werden bereinigt

## Fehlerbehandlung

| Fehler | Verhalten |
|--------|-----------|
| Dokument geloescht | Skip mit Warning |
| Encoding-Fehler | Zeichen ersetzen mit ? |
| Duplikat (bereits exportiert) | Skip |
| Leere Buchungsliste | Leere CSV (nur Header) |

## Konfiguration

```env
# DATEV Export
DATEV_DEFAULT_CREDITOR_ACCOUNT=70000
DATEV_DEFAULT_DEBITOR_ACCOUNT=10000
DATEV_EXPORT_BATCH_SIZE=500
DATEV_EXPORT_TIMEOUT_SECONDS=300

# Mandanten-Info
DATEV_CONSULTANT_NUMBER=12345
DATEV_CLIENT_NUMBER=67890
```

## Tests

```bash
# Unit Tests
pytest tests/unit/services/datev/ -v

# Spezifische Compliance Tests
pytest tests/unit/services/datev/test_export_comprehensive.py -v

# Coverage
pytest tests/unit/services/datev/ --cov=app.services.datev --cov-report=html
```

## Compliance

Der Export entspricht:
- DATEV Format-Spezifikation Version 700
- GoBD-Anforderungen (Unveraenderbarkeit)
- BSI Grundschutz (Encoding, keine Injection)

# Document Lineage Timeline (NEU: Februar 2026)

**Status**: Production-Ready
**Migration**: 147 (add_document_lineage)

**Core Services** (`app/services/lineage/`):
- `DocumentLineageService` - Lineage-Event Recording und Timeline-Abruf
- Integration Helpers - record_document_import, record_ocr_result, etc.

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Import-Tracking | Email, Ordner, API, Manueller Upload |
| OCR-Verarbeitung | Start, Ende, Dauer, Konfidenz, Backend |
| Klassifikation | Dokumenttyp mit Konfidenz |
| Entity-Linking | Verknuepfung mit Geschaeftspartnern |
| Modifikationen | Aenderungen mit Benutzer und Zeitstempel |
| Export-History | Alle Exporte mit Format und Ziel |

**Event Types**:
- `import` - Dokument importiert
- `ocr_start`, `ocr_complete`, `ocr_failed` - OCR-Verarbeitung
- `classification` - Dokumenttyp klassifiziert
- `extraction` - Daten extrahiert
- `entity_link`, `entity_unlink` - Entity-Verknuepfung
- `modification` - Manuelle Aenderung
- `approval`, `rejection`, `escalation` - Workflow
- `export` - Dokument exportiert
- `archive`, `restore` - Archivierung
- `soft_delete`, `hard_delete` - Loeschung (DSGVO)

**API Endpoints**:
- `GET /api/v1/documents/{id}/lineage` - Vollstaendige Timeline
- `GET /api/v1/documents/{id}/lineage/stats` - Aggregierte Statistiken
- `GET /api/v1/documents/{id}/lineage/summary` - Lineage-Zusammenfassung
- `GET /api/v1/documents/{id}/lineage/export` - Export als JSON/PDF
- `GET /api/v1/documents/lineage/event-types` - Verfuegbare Event-Typen
- `GET /api/v1/documents/lineage/import-source-types` - Import-Quelltypen

**Datenmodell** (2 neue Tabellen):
- `document_lineage_events` - Alle Ereignisse mit JSONB-Details
- `document_lineage_summaries` - Cache fuer schnelle Abfragen

**Integration in bestehende Services**:
```python
from app.services.lineage import (
    record_document_import,
    record_ocr_result,
    record_entity_linking,
    record_document_modification,
)

# Nach Document-Upload
await record_document_import(db, document_id, company_id, ImportSourceType.MANUAL_UPLOAD, user_id=user_id)

# Nach OCR-Verarbeitung
await record_ocr_result(db, document_id, company_id, backend="deepseek", duration_ms=1500, confidence=0.95)

# Nach Entity-Linking
await record_entity_linking(db, document_id, company_id, entity_id, confidence=0.85, match_type="customer_number", reason="Matched by customer number")
```

**SECURITY**: Niemals PII in Lineage-Events speichern! Details werden automatisch gefiltert.

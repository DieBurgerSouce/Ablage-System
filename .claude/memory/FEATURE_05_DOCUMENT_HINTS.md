# Feature #5: Proaktive Dokument-Hinweise

**Status**: ✅ Implemented
**Datum**: 2026-02-13
**Version**: 1.0

---

## Überblick

Implementierung eines **Document Hints Service** zur Aggregation proaktiver, kontextbezogener Hinweise für Dokumente. Der Service analysiert verschiedene Datenquellen und generiert Warnungen und Empfehlungen, die Benutzern helfen, Probleme frühzeitig zu erkennen.

---

## Implementierte Komponenten

### 1. Document Hints Service
**Pfad**: `app/services/document_hints_service.py`

**Klassen**:
- `DocumentHintsService` - Hauptservice für Hint-Aggregation
- `DocumentHint` - Dataclass für einzelnen Hint
- `HintSummary` - Dataclass für Dashboard-Statistiken

**Hint-Kategorien** (8 Typen):
1. **MISSING_DOCUMENT** - Fehlende Dokumente in Auftragsketten
2. **SKONTO_DEADLINE** - Ablaufende Skonto-Fristen (Integration mit skonto_service)
3. **ENTITY_RISK** - Risiko-Scores von Geschäftspartnern (Integration mit risk_scoring_service)
4. **PAYMENT_OVERDUE** - Überfällige Zahlungen
5. **OCR_QUALITY** - Niedrige OCR-Konfidenz
6. **DUPLICATE_SUSPECT** - Mögliche Duplikate (JSONB-Query)
7. **COMPLIANCE** - Fehlende GoBD-Pflichtfelder
8. **ACTION_REQUIRED** - Erforderliche Freigaben (z.B. Rechnungen >10.000 EUR)

**Severity-Stufen**:
- `INFO` - Informativ
- `WARNING` - Warnung
- `CRITICAL` - Kritisch

**Kern-Methoden**:
```python
async def get_hints_for_document(document_id: UUID, company_id: UUID) -> List[DocumentHint]
async def get_hints_batch(document_ids: List[UUID], company_id: UUID) -> Dict[UUID, List[DocumentHint]]
async def get_hint_summary(company_id: UUID) -> HintSummary
```

**Design-Patterns**:
- Dependency Injection via factory function
- Multi-tenant isolation (company_id in allen Queries)
- Safe error handling mit structlog
- NEVER log PII (keine customer_ids, IBANs, VAT-IDs im Log)

---

### 2. API Endpoints
**Pfad**: `app/api/v1/document_hints.py`

**Endpoints**:

#### GET `/api/v1/documents/{document_id}/hints`
- Holt alle Hints für ein einzelnes Dokument
- Response: `DocumentHintsResponse` mit Liste von Hints

#### POST `/api/v1/documents/hints/batch`
- Batch-Operation für mehrere Dokumente
- Request: `BatchHintsRequest` mit document_ids
- Response: `BatchHintsResponse` mit Dictionary document_id → Hints

#### GET `/api/v1/documents/hints/summary`
- Dashboard-Zusammenfassung aller Hints
- Response: `HintSummarySchema` mit Statistiken nach Kategorie/Severity

**Schemas**:
- `DocumentHintSchema` - Einzelner Hint
- `DocumentHintsResponse` - Response für einzelnes Dokument
- `BatchHintsRequest` - Request für Batch
- `BatchHintsResponse` - Response für Batch
- `HintSummarySchema` - Zusammenfassung

**Security**:
- Alle Endpoints erfordern Authentication (`get_current_user`)
- Multi-tenant Isolation via `company_id`
- Error handling mit `safe_error_detail` (keine Stack Traces im Response)

---

### 3. Integration in main.py
**Änderungen**:
- Import hinzugefügt (Zeile ~943)
- Router registriert (Zeile ~1171)

```python
from app.api.v1.document_hints import router as document_hints_router
app.include_router(document_hints_router, prefix="/api/v1")
```

---

## Technische Details

### Datenquellen

| Hint-Typ | Datenquelle | Query-Typ |
|----------|-------------|-----------|
| MISSING_DOCUMENT | Document.chain_id, DocumentType | JOIN + COUNT |
| SKONTO_DEADLINE | InvoiceTracking.skonto_deadline | JOIN + datetime comparison |
| ENTITY_RISK | BusinessEntity.risk_score, InvoiceTracking | JOIN + aggregation |
| PAYMENT_OVERDUE | InvoiceTracking.due_date, status | datetime comparison |
| OCR_QUALITY | Document.ocr_confidence | threshold check |
| DUPLICATE_SUSPECT | Document.extracted_data['invoice_number'] | JSONB query |
| COMPLIANCE | Document.extracted_data (Pflichtfelder) | JSONB key check |
| ACTION_REQUIRED | Document.extracted_data['total_amount'] | threshold check |

### Performance-Optimierung

**Implemented**:
- Lazy loading (nur wenn Hints angefordert)
- Batch-Endpoint für Multi-Document Queries
- Index-basierte Queries (chain_id, skonto_deadline, due_date)
- Limit auf get_hint_summary (max 1000 Dokumente)

**Future Optimization** (bei Bedarf):
- Redis-Caching für häufig angefragte Hints
- Celery Background Task für Hint-Berechnung
- WebSocket Push für neue kritische Hints

### Multi-Tenant Security

**Alle Service-Methoden** prüfen `company_id`:
```python
Document.company_id == company_id
InvoiceTracking.company_id == company_id
```

**CRITICAL**: Niemals company_id aus User-Input übernehmen - immer aus `current_user.company_id`.

---

## Abhängigkeiten

**Services**:
- `app/services/risk_scoring_service.py` - Risk Score Berechnung
- `app/services/banking/skonto_service.py` - Skonto-Deadline Monitoring
- `app/services/document_entity_linker_service.py` - Entity Linking

**Models**:
- `Document` - Dokumente
- `InvoiceTracking` - Rechnungs-Status
- `BusinessEntity` - Geschäftspartner
- `DocumentType` (Enum)
- `InvoiceStatus` (Enum)

**Core**:
- `app/core/safe_errors.py` - Error Handling
- `app/api/dependencies.py` - Authentication

---

## Testing

### Manual Testing via Swagger UI

1. **GET /api/v1/documents/{document_id}/hints**
   - Test mit vorhandener Rechnung
   - Erwartung: Hints für Skonto, Risiko, etc.

2. **POST /api/v1/documents/hints/batch**
   - Test mit 3-5 document_ids
   - Erwartung: Dictionary mit Hints pro Dokument

3. **GET /api/v1/documents/hints/summary**
   - Test für Company
   - Erwartung: Statistiken nach Kategorie/Severity

### Unit Tests (TODO)

Erstelle: `tests/unit/services/test_document_hints_service.py`

**Test Cases**:
- `test_skonto_deadline_hint_critical` - Skonto läuft in 1 Tag ab
- `test_skonto_deadline_hint_warning` - Skonto läuft in 5 Tagen ab
- `test_entity_risk_critical` - Risk Score >= 75
- `test_payment_overdue_critical` - 31 Tage überfällig
- `test_ocr_quality_warning` - Konfidenz < 0.70
- `test_duplicate_suspect` - Gleiche Rechnungsnummer
- `test_compliance_missing_fields` - GoBD Pflichtfelder fehlen
- `test_action_required_approval` - Rechnung > 10.000 EUR
- `test_batch_hints` - Mehrere Dokumente
- `test_hint_summary` - Dashboard-Statistiken

### Integration Tests (TODO)

Erstelle: `tests/integration/test_document_hints_api.py`

---

## Patterns und Best Practices

### ✅ GOOD Patterns
- Dataclasses für strukturierte Daten
- Factory functions für Dependency Injection
- Enum für Kategorien/Severity (Typ-Sicherheit)
- `typing.List`, `typing.Dict` (Python 3.11 kompatibel)
- Safe error handling (kein PII im Log)
- Multi-tenant isolation (company_id in allen Queries)
- German user-facing messages

### ✅ Code Quality
- NEVER use `Any` type
- Type hints auf allen Funktionen
- Structlog für logging
- Safe error log (keine Stack Traces)
- JSONB queries für extracted_data

### ✅ Security
- Authentication required (get_current_user)
- Multi-tenant: company_id aus current_user
- Keine PII im Log (customer numbers, IBANs, VAT-IDs)
- Safe error details (keine internen Fehler im Response)

---

## Frontend Integration (Next Steps)

### 1. Document Hints Badge
```tsx
// Zeige Anzahl kritischer Hints auf Dokument-Card
<Badge variant="destructive">
  {hints.filter(h => h.severity === 'critical').length}
</Badge>
```

### 2. Hints Panel
```tsx
// Expandierbares Panel mit allen Hints
<HintsPanel hints={hints}>
  {hints.map(hint => (
    <HintCard
      category={hint.category}
      severity={hint.severity}
      title={hint.title}
      message={hint.message}
      actionLabel={hint.action_label}
      onAction={() => handleAction(hint.action_type, hint.action_data)}
    />
  ))}
</HintsPanel>
```

### 3. Dashboard Widget
```tsx
// Summary Widget für Dashboard
<HintsSummaryWidget>
  <HintStat category="skonto_deadline" count={summary.by_category.skonto_deadline} />
  <HintStat category="payment_overdue" count={summary.by_category.payment_overdue} />
  <HintStat severity="critical" count={summary.critical_count} />
</HintsSummaryWidget>
```

### 4. TanStack Query Hook
```tsx
const { data: hints } = useQuery({
  queryKey: ['document-hints', documentId],
  queryFn: () => api.getDocumentHints(documentId),
  refetchInterval: 60000, // Refresh every minute
})
```

---

## Erweiterungsmöglichkeiten (Future Features)

### 1. Real-time Hints via WebSocket
```python
# In websocket.py
async def send_hint_notification(document_id: UUID, hint: DocumentHint):
    await manager.broadcast_to_company({
        "type": "hint_created",
        "document_id": str(document_id),
        "hint": hint.to_dict()
    })
```

### 2. Hint Preferences
```python
# Benutzer kann Hints deaktivieren
user.preferences = {
    "hints": {
        "enabled_categories": ["skonto_deadline", "payment_overdue"],
        "min_severity": "warning"
    }
}
```

### 3. Hint Actions Automation
```python
# Automatische Aktionen bei kritischen Hints
if hint.severity == HintSeverity.CRITICAL and hint.action_type == "send_dunning":
    await dunning_service.auto_send_dunning(invoice_id)
```

### 4. ML-basierte Hints
```python
# Predictive Hints via ML-Modell
hint = await ml_service.predict_payment_delay(invoice_id)
if hint.confidence > 0.80:
    hints.append(hint)
```

---

## Deployment Notes

### Database
- Keine Migrations erforderlich (nutzt bestehende Tabellen)
- Index-optimiert (chain_id, skonto_deadline, due_date bereits vorhanden)

### API
- Neue Endpoints automatisch in OpenAPI Docs verfügbar
- Tag: "Document Hints"

### Testing
```bash
# Start Backend
docker-compose up -d backend

# Test Endpoints via Swagger
http://localhost:8000/docs#/Document%20Hints
```

---

## Changelog

### 2026-02-13 - Initial Implementation (v1.0)
- ✅ DocumentHintsService mit 8 Hint-Typen implementiert
- ✅ 3 API Endpoints (single, batch, summary)
- ✅ Integration in main.py
- ✅ Multi-tenant security
- ✅ Production-ready code quality
- ✅ German user-facing messages

---

## Referenzen

**Code Files**:
- Service: `app/services/document_hints_service.py` (543 lines)
- API: `app/api/v1/document_hints.py` (221 lines)
- Main: `app/main.py` (Import + Registration)

**Documentation**:
- `.claude/Docs/Features/Document-Hints.md` (dieses Dokument)

**Related Features**:
- Risk Scoring: `.claude/Docs/Features/Entity-Risk-Scoring.md`
- Skonto Tracking: `.claude/Docs/Features/Skonto-Tracking.md`
- Document Chains: `.claude/Docs/Features/Document-Chains.md`

---

**Feinpoliert und durchdacht - Enterprise-grade Document Hints.**

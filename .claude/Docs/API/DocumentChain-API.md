# Document Chain API

## Übersicht

Die Document Chain API ermöglicht die Verfolgung von Dokumentenketten (Auftragsketten) im Geschäftsprozess. Sie verknüpft zusammengehörige Dokumente wie Angebot → Auftrag → Lieferschein → Rechnung und erkennt Abweichungen.

**Basis-URL**: `/api/v1/document-chains`
**Authentifizierung**: JWT Bearer Token erforderlich
**Multi-Tenant**: Alle Operationen sind auf die aktuelle Company beschränkt

---

## Dokumententypen in der Kette

| Typ | Deutsch | Position |
|-----|---------|----------|
| `quote` | Angebot | 1 |
| `order` | Auftrag/Bestellung | 2 |
| `delivery_note` | Lieferschein | 3 |
| `invoice` | Rechnung | 4 |
| `credit_note` | Gutschrift | 5 |

---

## Beziehungstypen

| Beziehung | Beschreibung |
|-----------|--------------|
| `quote_to_order` | Angebot zu Auftrag |
| `order_to_delivery` | Auftrag zu Lieferschein |
| `delivery_to_invoice` | Lieferschein zu Rechnung |
| `invoice_to_credit_note` | Rechnung zu Gutschrift |
| `quote_to_invoice` | Direkt Angebot zu Rechnung |

---

## Endpunkte

### Ketten erstellen & abrufen

#### POST /document-chains

Erstellt eine neue Dokumentenkette.

**Request Body**:
```json
{
  "name": "Projekt Alpha - Büroausstattung",
  "description": "Lieferung Büromöbel für Standort München",
  "entity_id": "550e8400-e29b-41d4-a716-446655440001",
  "initial_document_id": "550e8400-e29b-41d4-a716-446655440002",
  "reference_number": "PROJ-2026-001",
  "expected_total": 15000.00,
  "currency": "EUR"
}
```

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "name": "Projekt Alpha - Büroausstattung",
  "status": "open",
  "documents_count": 1,
  "progress": {
    "quote": true,
    "order": false,
    "delivery_note": false,
    "invoice": false
  },
  "created_at": "2026-01-27T10:00:00Z"
}
```

---

#### GET /document-chains

Listet alle Dokumentenketten auf.

**Query-Parameter**:
| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `skip` | int | Pagination Offset (default: 0) |
| `limit` | int | Anzahl Ergebnisse (default: 50, max: 100) |
| `status` | string | `open`, `complete`, `partial`, `disputed` |
| `entity_id` | UUID | Ketten für Geschäftspartner |
| `from_date` | date | Erstellt ab (YYYY-MM-DD) |
| `to_date` | date | Erstellt bis (YYYY-MM-DD) |
| `has_discrepancies` | bool | Nur Ketten mit Abweichungen |
| `search` | string | Suche in Name/Referenznummer |

**Response** (200):
```json
{
  "chains": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440010",
      "name": "Projekt Alpha - Büroausstattung",
      "reference_number": "PROJ-2026-001",
      "entity": {
        "id": "...",
        "name_masked": "M***r GmbH"
      },
      "status": "partial",
      "documents_count": 3,
      "progress": {
        "quote": true,
        "order": true,
        "delivery_note": true,
        "invoice": false
      },
      "expected_total": 15000.00,
      "current_total": 14850.00,
      "discrepancy_count": 1,
      "created_at": "2026-01-27T10:00:00Z",
      "last_activity_at": "2026-01-27T14:30:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "pages": 1
}
```

---

#### GET /document-chains/{chain_id}

Ruft eine Kette mit allen Details ab.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440010",
  "name": "Projekt Alpha - Büroausstattung",
  "description": "Lieferung Büromöbel für Standort München",
  "reference_number": "PROJ-2026-001",
  "entity": {
    "id": "...",
    "name": "Müller Office GmbH",
    "customer_number": "K-12345"
  },
  "status": "partial",
  "expected_total": 15000.00,
  "currency": "EUR",
  "documents": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "type": "quote",
      "document_number": "ANG-2026-001",
      "date": "2026-01-15",
      "amount": 15000.00,
      "status": "accepted",
      "linked_at": "2026-01-27T10:00:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "type": "order",
      "document_number": "AUF-2026-001",
      "date": "2026-01-18",
      "amount": 15000.00,
      "status": "confirmed",
      "linked_at": "2026-01-27T10:15:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440004",
      "type": "delivery_note",
      "document_number": "LS-2026-001",
      "date": "2026-01-25",
      "amount": 14850.00,
      "status": "delivered",
      "linked_at": "2026-01-27T14:30:00Z"
    }
  ],
  "relationships": [
    {
      "type": "quote_to_order",
      "source_id": "550e8400-e29b-41d4-a716-446655440002",
      "target_id": "550e8400-e29b-41d4-a716-446655440003",
      "confidence": 0.98,
      "match_method": "reference_number",
      "created_at": "2026-01-27T10:15:00Z"
    },
    {
      "type": "order_to_delivery",
      "source_id": "550e8400-e29b-41d4-a716-446655440003",
      "target_id": "550e8400-e29b-41d4-a716-446655440004",
      "confidence": 0.95,
      "match_method": "customer_and_amount",
      "created_at": "2026-01-27T14:30:00Z"
    }
  ],
  "progress": {
    "quote": true,
    "order": true,
    "delivery_note": true,
    "invoice": false,
    "expected_next": "invoice",
    "completion_percent": 75
  },
  "timeline": [
    {
      "date": "2026-01-15",
      "event": "quote_created",
      "document_id": "...",
      "description": "Angebot erstellt"
    },
    {
      "date": "2026-01-18",
      "event": "order_linked",
      "document_id": "...",
      "description": "Auftrag verknüpft"
    },
    {
      "date": "2026-01-25",
      "event": "delivery_linked",
      "document_id": "...",
      "description": "Lieferschein verknüpft"
    }
  ],
  "created_at": "2026-01-27T10:00:00Z",
  "updated_at": "2026-01-27T14:30:00Z"
}
```

---

### Dokumente verknüpfen

#### POST /document-chains/link

Verknüpft ein Dokument mit einer bestehenden Kette.

**Request Body**:
```json
{
  "chain_id": "550e8400-e29b-41d4-a716-446655440010",
  "document_id": "550e8400-e29b-41d4-a716-446655440005",
  "relationship_type": "delivery_to_invoice",
  "source_document_id": "550e8400-e29b-41d4-a716-446655440004"
}
```

**Response** (200):
```json
{
  "chain_id": "550e8400-e29b-41d4-a716-446655440010",
  "document_id": "550e8400-e29b-41d4-a716-446655440005",
  "relationship": {
    "type": "delivery_to_invoice",
    "source_id": "550e8400-e29b-41d4-a716-446655440004",
    "target_id": "550e8400-e29b-41d4-a716-446655440005",
    "confidence": 1.0,
    "match_method": "manual"
  },
  "chain_status": "complete",
  "discrepancies_detected": 1
}
```

---

### Auto-Matching

#### GET /document-chains/auto-match/{document_id}

Findet automatisch passende Ketten für ein Dokument.

**Response** (200):
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440006",
  "document_type": "invoice",
  "matches": [
    {
      "chain_id": "550e8400-e29b-41d4-a716-446655440010",
      "chain_name": "Projekt Alpha - Büroausstattung",
      "confidence": 0.95,
      "match_reasons": [
        {
          "criterion": "reference_number",
          "value": "PROJ-2026-001",
          "weight": 0.4
        },
        {
          "criterion": "entity_match",
          "value": "Müller Office GmbH",
          "weight": 0.3
        },
        {
          "criterion": "amount_similarity",
          "value": "98.5%",
          "weight": 0.2
        },
        {
          "criterion": "date_sequence",
          "value": "valid",
          "weight": 0.1
        }
      ],
      "suggested_relationship": "delivery_to_invoice",
      "suggested_source_document": {
        "id": "550e8400-e29b-41d4-a716-446655440004",
        "type": "delivery_note",
        "number": "LS-2026-001"
      }
    }
  ],
  "no_match_reason": null
}
```

**Wenn kein Match gefunden**:
```json
{
  "document_id": "...",
  "document_type": "invoice",
  "matches": [],
  "no_match_reason": "Keine Kette mit passender Referenznummer oder Entity gefunden"
}
```

---

### Abweichungen

#### GET /document-chains/{chain_id}/discrepancies

Listet Abweichungen innerhalb einer Kette auf.

**Response** (200):
```json
{
  "chain_id": "550e8400-e29b-41d4-a716-446655440010",
  "discrepancies": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440020",
      "type": "amount_mismatch",
      "severity": "medium",
      "description": "Betragsdifferenz zwischen Auftrag und Lieferschein",
      "details": {
        "source_document": {
          "id": "550e8400-e29b-41d4-a716-446655440003",
          "type": "order",
          "number": "AUF-2026-001",
          "amount": 15000.00
        },
        "target_document": {
          "id": "550e8400-e29b-41d4-a716-446655440004",
          "type": "delivery_note",
          "number": "LS-2026-001",
          "amount": 14850.00
        },
        "difference": -150.00,
        "difference_percent": -1.0
      },
      "status": "open",
      "resolution": null,
      "detected_at": "2026-01-27T14:30:00Z"
    }
  ],
  "summary": {
    "total": 1,
    "by_severity": {
      "high": 0,
      "medium": 1,
      "low": 0
    },
    "by_type": {
      "amount_mismatch": 1,
      "quantity_mismatch": 0,
      "date_sequence_error": 0,
      "missing_document": 0
    }
  }
}
```

---

#### POST /document-chains/{chain_id}/discrepancies/{discrepancy_id}/resolve

Löst eine Abweichung auf.

**Request Body**:
```json
{
  "resolution": "accepted",
  "comment": "Teillieferung - Restlieferung folgt",
  "expected_resolution_document_id": null
}
```

**Resolution Types**:
- `accepted` - Abweichung akzeptiert
- `corrected` - Dokument korrigiert
- `pending_followup` - Nachlieferung erwartet
- `disputed` - Wird mit Lieferant geklärt

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440020",
  "status": "resolved",
  "resolution": "accepted",
  "resolved_by": "Max Mustermann",
  "resolved_at": "2026-01-27T15:00:00Z"
}
```

---

## Matching-Kriterien

### Confidence-Berechnung

| Kriterium | Gewicht | Beschreibung |
|-----------|---------|--------------|
| Referenznummer | 40% | Exakte Übereinstimmung |
| Entity-Match | 30% | Gleicher Geschäftspartner |
| Betrags-Ähnlichkeit | 20% | Betrag ±5% |
| Datumssequenz | 10% | Logische Reihenfolge |

### Minimum Confidence

| Matching-Methode | Min. Confidence |
|------------------|-----------------|
| `reference_number` | 95% |
| `customer_and_amount` | 85% |
| `amount_only` | 70% |

---

## Abweichungstypen

| Typ | Schweregrad | Beschreibung |
|-----|-------------|--------------|
| `amount_mismatch` | medium/high | Betragsdifferenz |
| `quantity_mismatch` | medium | Mengendifferenz |
| `date_sequence_error` | low | Ungültige Datumsreihenfolge |
| `missing_document` | high | Fehlendes Dokument in Kette |
| `entity_mismatch` | high | Unterschiedliche Geschäftspartner |

### Schweregrad-Regeln

- **High**: Differenz > 5% oder kritische Fehler
- **Medium**: Differenz 1-5%
- **Low**: Differenz < 1% oder Warnungen

---

## Ketten-Status

| Status | Beschreibung |
|--------|--------------|
| `open` | Kette aktiv, Dokumente werden erwartet |
| `partial` | Teilweise vollständig |
| `complete` | Alle erwarteten Dokumente vorhanden |
| `disputed` | Ungelöste Abweichungen vorhanden |
| `closed` | Manuell geschlossen |

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `CHAIN_NOT_FOUND` | 404 | Kette nicht gefunden |
| `CHAIN_DOCUMENT_NOT_FOUND` | 404 | Dokument nicht gefunden |
| `CHAIN_DOCUMENT_ALREADY_LINKED` | 409 | Dokument bereits verknüpft |
| `CHAIN_INVALID_RELATIONSHIP` | 422 | Ungültige Beziehung |
| `CHAIN_SEQUENCE_ERROR` | 422 | Ungültige Dokumentenreihenfolge |
| `CHAIN_DISCREPANCY_NOT_FOUND` | 404 | Abweichung nicht gefunden |

---

## Sicherheitshinweise

1. **Multi-Tenant**: Strikte Company-Isolation
2. **Audit-Trail**: Alle Verknüpfungen werden protokolliert
3. **PII-Schutz**: Entity-Namen können maskiert werden
4. **Berechtigungen**: Nur autorisierte Benutzer können verknüpfen

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |

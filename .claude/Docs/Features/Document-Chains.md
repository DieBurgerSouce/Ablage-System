# Document Chain Tracking (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: 095 (document_chain_tracking)

**Core Service**: `DocumentChainService`

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Auftragsketten | Angebot -> Auftrag -> Lieferschein -> Rechnung |
| Auto-Matching | Automatische Erkennung zusammengehoeriger Dokumente |
| Abweichungserkennung | Warnung bei Differenzen (Betraege, Mengen) |
| Chain-Status | Uebersicht ueber Kettenfortschritt |

**Relationship Types**:
- `QUOTE_TO_ORDER` - Angebot zu Auftrag
- `ORDER_TO_DELIVERY` - Auftrag zu Lieferschein
- `DELIVERY_TO_INVOICE` - Lieferschein zu Rechnung
- `QUOTE_TO_INVOICE` - Direktverknuepfung Angebot zu Rechnung

**API Endpoints**:
- `POST /api/v1/document-chains` - Neue Kette erstellen
- `GET /api/v1/document-chains` - Ketten auflisten
- `GET /api/v1/document-chains/{chain_id}` - Ketten-Details
- `POST /api/v1/document-chains/link` - Dokumente verknuepfen
- `GET /api/v1/document-chains/auto-match/{document_id}` - Auto-Match
- `GET /api/v1/document-chains/{chain_id}/discrepancies` - Abweichungen

**Matching-Kriterien (Confidence)**:
- Referenznummer identisch: 95%+ Confidence
- Kundennummer + Betrag: 85%+ Confidence
- Nur Betrag aehnlich: 70%+ Confidence

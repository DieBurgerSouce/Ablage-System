# Entity Risk Scoring (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: 092 (entity_risk_scoring), 093 (invoice_tracking)

**Core Services**:
- `RiskScoringService` - Score-Berechnung (0-100) basierend auf 5 Faktoren
- `InvoiceTracking` - Rechnungsverfolgung mit Mahnstufen

**Risk Faktoren (Gewichtung)**:
| Faktor | Gewicht | Beschreibung |
|--------|---------|--------------|
| payment_delay | 35% | Durchschnittliche Zahlungsverzoegerung |
| default_rate | 25% | Ausfallrate (ueberfaellige/gesamt) |
| invoice_volume | 15% | Gesamtvolumen (hoeher = weniger Risiko) |
| document_frequency | 10% | Dokumente/Monat (regelmaessig = weniger Risiko) |
| relationship_age | 15% | Beziehungsdauer (laenger = weniger Risiko) |

**Celery Tasks (automatisch)**:
- `risk_scoring.calculate_all` - Taeglich 02:00 (maintenance queue)
- `risk_scoring.calculate_single` - Nach Invoice-Updates (metadata queue)
- `risk_scoring.check_high_risk_entities` - Nach Batch (threshold: 75)
- `risk_scoring.generate_statistics` - Woechentlich (Reporting)

**API Endpoints**: `/api/v1/invoices/*` (CRUD + mark-paid + increase-dunning)

**SECURITY**: NIEMALS Entity-Namen in Logs oder Responses (PII)!

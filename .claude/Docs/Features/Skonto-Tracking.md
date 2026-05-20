# Skonto-Tracking (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: 094 (skonto_and_partial_payments)

**Core Services**:
- `SkontoService` - Skonto-Berechnung, Deadline-Tracking, Auto-Detection
- `PartialPaymentService` - Teilzahlungs-Verwaltung, Bank-Reconciliation

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Skonto-Berechnung | Automatische Berechnung von Skonto-Betrag und Deadline |
| Deadline-Alerts | Warnungen vor ablaufenden Skonto-Fristen |
| Auto-Detection | Erkennung von Skonto-Bedingungen aus OCR-Text |
| Teilzahlungen | Mehrere Zahlungen pro Rechnung, Status-Updates |
| Bank-Reconciliation | Verknuepfung mit Bank-Transaktionen |

**API Endpoints**:
- `GET /api/v1/invoices/{id}/skonto` - Skonto-Informationen abrufen
- `PATCH /api/v1/invoices/{id}/skonto` - Skonto-Bedingungen aktualisieren
- `POST /api/v1/invoices/{id}/apply-skonto` - Skonto anwenden
- `GET /api/v1/invoices/skonto/upcoming` - Bevorstehende Skonto-Fristen
- `POST /api/v1/invoices/{id}/payments` - Teilzahlung erfassen
- `GET /api/v1/invoices/{id}/payments` - Zahlungsuebersicht

**Datenmodell (InvoiceTracking erweitert)**:
```
skonto_percentage: Float    # z.B. 2.0 fuer 2%
skonto_days: Integer        # Tage fuer Skonto-Frist
skonto_deadline: DateTime   # Berechnete Frist
skonto_amount: Float        # Berechneter Betrag
skonto_used: Boolean        # True wenn genutzt
outstanding_amount: Float   # Ausstehender Betrag
is_partial_payment: Boolean # True bei Teilzahlungen
```

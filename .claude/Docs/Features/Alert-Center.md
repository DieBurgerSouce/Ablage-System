# Alert Center (NEU: Januar 2026)

**Status**: Production-Ready
**Migration**: 117 (add_alerts_center)

**Core Service**: `AlertCenterService` (`app/services/alert_center_service.py`)

**Features**:
| Feature | Beschreibung |
|---------|--------------|
| Kategorisierung | 8 Alert-Kategorien (fraud, risk, compliance, deadline, system, security, quality, workflow) |
| Schweregrade | 5 Stufen (info, low, medium, high, critical) |
| Status-Workflow | new -> acknowledged -> in_progress -> resolved/dismissed/escalated |
| Bulk Actions | Massenaktionen auf mehrere Alerts |
| Email-Digest | Konfigurierbare Zusammenfassungen (taeglich/woechentlich) |

**Alert-Kategorien**:
- `fraud` - Betrugsverdacht (FRAUD_001 bis FRAUD_004)
- `risk` - Risikowarnungen (RISK_001 bis RISK_004)
- `compliance` - Compliance-Verletzungen (COMP_001 bis COMP_005)
- `deadline` - Fristwarnungen (DEAD_001 bis DEAD_004)
- `system` - Systemwarnungen (SYS_001 bis SYS_005)
- `security` - Sicherheitswarnungen (SEC_001 bis SEC_004)
- `quality` - Qualitaetswarnungen (QUAL_001 bis QUAL_003)
- `workflow` - Workflow-Alerts (WORK_001 bis WORK_003)

**API Endpoints**:
- `GET /api/v1/alerts` - Alert-Liste mit Filterung und Paginierung
- `GET /api/v1/alerts/stats` - Dashboard-Statistiken
- `GET /api/v1/alerts/counts` - Zaehler nach Kategorie/Schweregrad/Status
- `GET /api/v1/alerts/{id}` - Einzelner Alert
- `POST /api/v1/alerts` - Manuellen Alert erstellen
- `POST /api/v1/alerts/{id}/acknowledge` - Als gelesen markieren
- `POST /api/v1/alerts/{id}/dismiss` - Verwerfen
- `POST /api/v1/alerts/{id}/resolve` - Als geloest markieren
- `POST /api/v1/alerts/{id}/escalate` - An Benutzer eskalieren
- `POST /api/v1/alerts/{id}/assign` - Benutzer zuweisen
- `POST /api/v1/alerts/bulk` - Massenaktionen

**Frontend**: `/alerts` - Vollstaendiges Dashboard mit:
- Statistik-Karten (total, new, critical, 24h)
- Kategorie-Zusammenfassung
- Filterbare Alert-Liste
- Quick-Actions (Acknowledge, Dismiss, Resolve)
- Detail-Dialog mit Kontext und Metadaten
- Bulk-Selection und Massenaktionen

**Datenmodell (Alert)**:
```python
id: UUID
alert_code: str              # z.B. FRAUD_001, RISK_002
title: str
message: str
category: AlertCategory      # fraud, risk, compliance, ...
severity: AlertSeverity      # info, low, medium, high, critical
status: AlertStatus          # new, acknowledged, resolved, ...
document_id: Optional[UUID]  # Verknuepftes Dokument
entity_id: Optional[UUID]    # Verknuepfter Geschaeftspartner
company_id: UUID             # Multi-Tenant
metadata: JSONB              # Kategorie-spezifische Daten
context: JSONB               # UI-Kontext
```

# Feature 05: Dashboard & KPIs

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P2 - Wichtig
> **Geschaetzter Aufwand**: 3-4 Wochen
> **Abhaengigkeiten**: Feature 01 (Multi-Firma), Feature 03 (Notifications)

---

## Executive Summary

Das Dashboard & KPIs Feature bietet eine zentrale Uebersicht ueber alle wichtigen Business-Kennzahlen. Ein Widget-System ermoeglicht personalisierte Dashboards, waehrend eine Power-BI-artige Filter-Engine flexible Auswertungen erlaubt. Berechtigungen steuern, welche Widgets fuer welche Rollen sichtbar sind.

**Business Value:**
- Alle wichtigen KPIs auf einen Blick
- Personalisierbare Dashboards
- Zeitraum-Vergleiche (YoY, MoM)
- Rollenbasierte Sichtbarkeit

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Widget-Katalog mit 8+ Widgets | MUSS | Alle Widgets verfuegbar |
| FR-02 | Drag & Drop Anordnung | MUSS | User kann Widgets verschieben |
| FR-03 | Zeitraum-Filter | MUSS | Beliebiger Zeitraum waehlbar |
| FR-04 | Zeitraum-Vergleich | SOLL | Vergleich mit Vorperiode |
| FR-05 | Multi-Firma Filter | MUSS | Pro Firma oder konsolidiert |
| FR-06 | Widget-Groessen | SOLL | Small, Medium, Large |
| FR-07 | Dashboard speichern | SOLL | Layouts persistieren |
| FR-08 | Berechtigungs-System | MUSS | Widgets nach Rolle |

---

## Widget-Katalog

| Widget | Beschreibung | Groesse | Berechtigung |
|--------|--------------|---------|--------------|
| Offene Posten | Ueberfaellige Rechnungen, Summen, Aging | M/L | Finanzen |
| Cashflow | Einnahmen/Ausgaben Trend Chart | M/L | Finanzen |
| Dokumente heute | Neu, verarbeitet, wartend | S/M | Alle |
| Erinnerungen | Anstehende Fristen | S/M | Alle |
| Lieferanten-KPI | Puenktlichkeit, Qualitaet | M | Einkauf |
| Firmen-Uebersicht | Kennzahlen pro Firma | L | GF |
| OCR-Status | Queue, Erfolgsrate | S | Admin |
| Validierung | Offene Reviews | S/M | Validierung |
| Umsatz-Trend | Monatlicher Umsatz | M/L | GF, Finanzen |
| Top-Kunden | Umsatzstaerkste Kunden | M | Vertrieb, GF |

---

## API-Spezifikation

### Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/dashboard/widgets` | Verfuegbare Widgets | Required |
| GET | `/api/v1/dashboard/layout` | User-Layout | Required |
| PUT | `/api/v1/dashboard/layout` | Layout speichern | Required |
| GET | `/api/v1/dashboard/widgets/{type}/data` | Widget-Daten | Required |
| GET | `/api/v1/dashboard/kpis` | Alle KPIs | Required |

### `GET /api/v1/dashboard/widgets/{type}/data`

**Query Parameters:**

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| from_date | date | Startzeitpunkt |
| to_date | date | Endzeitpunkt |
| compare_from | date | Vergleichs-Start |
| compare_to | date | Vergleichs-Ende |
| company_ids | list | Firmen-Filter |

**Response (200 OK) - Beispiel "offene_posten":**
```json
{
  "widget_type": "offene_posten",
  "period": {"from": "2026-01-01", "to": "2026-01-31"},
  "data": {
    "total_open": 45670.50,
    "total_overdue": 12340.00,
    "count_open": 23,
    "count_overdue": 5,
    "aging": {
      "0-30": {"count": 15, "amount": 28000.00},
      "31-60": {"count": 5, "amount": 12000.00},
      "61-90": {"count": 2, "amount": 4000.00},
      "90+": {"count": 1, "amount": 1670.50}
    }
  },
  "comparison": {
    "total_open_change": -5.2,
    "total_overdue_change": 12.8
  }
}
```

---

## Datenbank-Schema

### `dashboard_layouts`

```sql
CREATE TABLE dashboard_layouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    name VARCHAR(100) DEFAULT 'Standard',
    is_default BOOLEAN DEFAULT false,

    widgets JSONB NOT NULL DEFAULT '[]',
    -- [{
    --   "type": "offene_posten",
    --   "position": {"x": 0, "y": 0},
    --   "size": "medium",
    --   "config": {"show_aging": true}
    -- }]

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT dashboard_layouts_user_name UNIQUE (user_id, name)
);
```

### `widget_permissions`

```sql
CREATE TABLE widget_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    widget_type VARCHAR(50) NOT NULL,
    role VARCHAR(50),  -- NULL = alle
    department VARCHAR(50),  -- NULL = alle

    CONSTRAINT widget_permissions_unique UNIQUE (widget_type, role, department)
);

-- Default-Berechtigungen
INSERT INTO widget_permissions (widget_type, role) VALUES
('offene_posten', 'buchhaltung'),
('offene_posten', 'geschaeftsfuehrung'),
('cashflow', 'buchhaltung'),
('cashflow', 'geschaeftsfuehrung'),
('dokumente_heute', NULL),  -- Alle
('erinnerungen', NULL),  -- Alle
('lieferanten_kpi', 'einkauf'),
('firmen_uebersicht', 'geschaeftsfuehrung'),
('ocr_status', 'admin'),
('validierung', 'validierung');
```

---

## Implementation Tasks

### Phase 1: Backend (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] DB Schema | Layouts + Permissions |
| 1.2 | [ ] Widget-Registry | Alle Widgets registriert |
| 1.3 | [ ] Data-Provider pro Widget | Daten korrekt berechnet |
| 1.4 | [ ] Filter-Engine | Zeitraum + Firma |
| 1.5 | [ ] Berechtigungs-Check | Nur erlaubte Widgets |

### Phase 2: Frontend (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Dashboard-Grid | react-grid-layout |
| 2.2 | [ ] Widget-Komponenten | 10 Widgets implementiert |
| 2.3 | [ ] Filter-Bar | Zeitraum + Firma |
| 2.4 | [ ] Widget-Katalog | Add Widget Dialog |
| 2.5 | [ ] Layout speichern | Persistenz funktioniert |

### Phase 3: Charts & Polish (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Recharts Integration | Charts rendern |
| 3.2 | [ ] Vergleichs-Anzeige | Delta % sichtbar |
| 3.3 | [ ] Loading States | Skeleton Loading |
| 3.4 | [ ] 4 Display-Modi | Alle Themes |

---

## Quality Gates

- [ ] Alle 10 Widgets funktionieren
- [ ] Drag & Drop reibungslos
- [ ] Filter wirken auf alle Widgets
- [ ] Berechtigungen greifen
- [ ] Performance < 2s fuer Dashboard-Load

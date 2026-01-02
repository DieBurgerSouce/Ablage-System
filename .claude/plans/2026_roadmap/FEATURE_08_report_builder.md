# Feature 08: Report-Builder

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P3 - Nice-to-Have
> **Geschaetzter Aufwand**: 3-4 Wochen
> **Abhaengigkeiten**: Feature 02 (GoBD), Feature 05 (Dashboard)

---

## Executive Summary

Der Report-Builder ermoeglicht die Erstellung von Standard- und Custom-Reports. Vordefinierte Templates decken 99% der SME-Anforderungen ab, waehrend ein visueller Builder flexible Custom-Reports erlaubt. Scheduled Exports senden Reports automatisch per E-Mail.

**Business Value:**
- Alle wichtigen Reports vordefiniert
- Custom Reports ohne Entwickler
- Automatischer Versand
- Steuerberater-ready Formate

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | 9 Standard-Templates | MUSS | Alle verfuegbar |
| FR-02 | PDF Export | MUSS | Professionelles Layout |
| FR-03 | Excel Export | MUSS | Formeln erhalten |
| FR-04 | Custom Report Builder | SOLL | Visueller Editor |
| FR-05 | Scheduled Exports | SOLL | Cron-basiert |
| FR-06 | E-Mail Versand | SOLL | An externe Empfaenger |
| FR-07 | Passwort-Schutz | KANN | PDFs verschluesselt |

---

## Standard-Templates

| Report | Beschreibung | Formate | Zielgruppe |
|--------|--------------|---------|------------|
| Offene Posten | Ueberfaellige Rechnungen | PDF, Excel | Buchhaltung |
| Eingangsrechnungen | Monatlich nach Lieferant | PDF, Excel | Buchhaltung |
| Ausgangsrechnungen | Monatlich nach Kunde | PDF, Excel | Vertrieb |
| USt-Vorbereitung | Fuer Steuerberater | PDF, Excel | Steuerberater |
| Lieferanten-Analyse | Performance, Volumen | PDF, Excel | Einkauf |
| Kunden-Analyse | Umsatz, Zahlungsverhalten | PDF, Excel | Vertrieb |
| Cashflow-Report | Ein-/Ausgaben ueber Zeit | PDF, Excel | GF |
| Dokumenten-Statistik | Volumen, OCR-Qualitaet | PDF | Admin |
| Vertrags-Uebersicht | Laufzeiten, Kuendigungen | PDF, Excel | GF |

---

## API-Spezifikation

### Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/reports/templates` | Alle Templates | Required |
| POST | `/api/v1/reports/generate` | Report generieren | Required |
| GET | `/api/v1/reports/custom` | Custom Reports | Required |
| POST | `/api/v1/reports/custom` | Custom erstellen | Required |
| GET | `/api/v1/reports/scheduled` | Geplante Reports | Required |
| POST | `/api/v1/reports/scheduled` | Report planen | Required |

### `POST /api/v1/reports/generate`

**Request:**
```json
{
  "template": "offene_posten",
  "format": "pdf",
  "filters": {
    "from_date": "2026-01-01",
    "to_date": "2026-01-31",
    "company_ids": ["company-uuid"]
  },
  "options": {
    "include_aging_chart": true,
    "group_by": "customer"
  }
}
```

**Response (200 OK):**
```json
{
  "report_id": "report-uuid",
  "download_url": "/api/v1/reports/download/report-uuid",
  "expires_at": "2026-01-16T10:00:00Z",
  "size_bytes": 245678,
  "pages": 12
}
```

---

## Datenbank-Schema

### `report_templates`

```sql
CREATE TABLE report_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50),

    query_definition JSONB NOT NULL,
    layout_definition JSONB NOT NULL,

    available_formats TEXT[] DEFAULT ARRAY['pdf', 'excel'],
    permissions JSONB DEFAULT '{}',

    is_system BOOLEAN DEFAULT false,
    created_by_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `scheduled_reports`

```sql
CREATE TABLE scheduled_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    template_id UUID REFERENCES report_templates(id),
    company_id UUID REFERENCES companies(id),

    name VARCHAR(255) NOT NULL,
    schedule VARCHAR(100) NOT NULL,  -- Cron format
    format VARCHAR(20) DEFAULT 'pdf',

    filters JSONB DEFAULT '{}',
    recipients JSONB NOT NULL,  -- [{email, name}]

    is_active BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,

    created_by_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Implementation Tasks

### Phase 1: Standard Templates (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] Report Engine | Basis-Rendering |
| 1.2 | [ ] PDF Generator | WeasyPrint/ReportLab |
| 1.3 | [ ] Excel Generator | openpyxl |
| 1.4 | [ ] 9 Templates | Alle implementiert |

### Phase 2: Custom Builder (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Query Builder | Visuelle Abfrage |
| 2.2 | [ ] Column Selector | Spalten waehlbar |
| 2.3 | [ ] Grouping | Gruppierung moeglich |
| 2.4 | [ ] Save Template | Als Custom speichern |

### Phase 3: Scheduling (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Celery Beat | Cron Schedule |
| 3.2 | [ ] E-Mail Versand | SMTP + Attachment |
| 3.3 | [ ] External Recipients | Beliebige E-Mails |
| 3.4 | [ ] Password Protection | PDF-Verschluesselung |

### Phase 4: Frontend (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 4.1 | [ ] Template Browser | Kategorisiert |
| 4.2 | [ ] Filter UI | Intuitiv |
| 4.3 | [ ] Custom Builder UI | Drag & Drop |
| 4.4 | [ ] Schedule UI | Cron-Helper |

---

## Quality Gates

- [ ] Alle 9 Templates generieren korrekt
- [ ] PDF/Excel Export funktioniert
- [ ] Scheduled Reports werden versendet
- [ ] Steuerberater-Format akzeptiert

# Executive Dashboard Feature

## Überblick

Das Executive Dashboard bietet Geschäftsführung eine kompakte Übersicht über die Dokumentenverarbeitung und Systemleistung mit KPIs, Trends und Abteilungsstatistiken.

**Status**: Production-Ready
**Erstellt**: 2026-02-06
**Stack**: FastAPI + React + TanStack Query + shadcn/ui + recharts

---

## Backend-Architektur

### Dateien

| Datei | Zweck |
|-------|-------|
| `app/api/schemas/reporting.py` | Pydantic v2 Schemas für Reporting-Responses |
| `app/api/v1/reporting.py` | FastAPI Router mit 4 Endpoints |
| `app/services/reporting/__init__.py` | Barrel Exports |
| `app/services/reporting/executive_dashboard_service.py` | Service-Logik für KPIs, Trends, Statistiken |

### API Endpoints

#### GET `/api/v1/reporting/kpis`

**Response**: `KPIResponse`

```json
{
  "documents_this_month": 1234,
  "documents_last_month": 1100,
  "documents_trend_percent": 12.2,
  "avg_processing_time_ms": 1850.0,
  "processing_time_trend_percent": -5.3,
  "ocr_accuracy": 0.965,
  "ocr_accuracy_trend": 2.1,
  "cost_per_document": 0.19,
  "active_users_count": 8,
  "pending_reviews": 23
}
```

**KPIs**:
- Dokumente aktueller/letzter Monat + Trend (%)
- Durchschnittliche Verarbeitungszeit + Trend (%)
- OCR-Genauigkeit + Trend (%)
- Geschätzte Kosten pro Dokument (0.10 EUR/Sekunde)
- Anzahl aktiver Benutzer (≥1 Upload im Monat)
- Ausstehende Prüfungen (Status PENDING/PROCESSING)

#### GET `/api/v1/reporting/departments`

**Response**: `List[DepartmentBreakdown]`

```json
[
  {
    "department": "INVOICE",
    "document_count": 456,
    "avg_processing_time_ms": 1650.0,
    "accuracy": 0.975,
    "pending_count": 12
  },
  {
    "department": "CONTRACT",
    "document_count": 234,
    "avg_processing_time_ms": 2100.0,
    "accuracy": 0.945,
    "pending_count": 5
  }
]
```

**Gruppierung**: Nach `document_type` (als Proxy für Abteilung/Bereich)

#### GET `/api/v1/reporting/trends/{metric}?days=30`

**Response**: `TrendResponse`

**Unterstützte Metriken**:
- `documents` - Anzahl Dokumente pro Tag
- `processing_time` - Durchschnittliche Verarbeitungszeit pro Tag (ms)
- `accuracy` - Durchschnittliche OCR-Genauigkeit pro Tag (0-1)

**Parameter**:
- `days` (Query): 1-365 (default: 30)

```json
{
  "metric": "documents",
  "data": [
    {"date": "2026-01-07", "value": 45.0},
    {"date": "2026-01-08", "value": 52.0},
    {"date": "2026-01-09", "value": 48.0}
  ],
  "period_days": 30
}
```

#### GET `/api/v1/reporting/summary`

**Response**: `ExecutiveSummaryResponse`

Kombiniert alle Daten:
- KPIs
- Abteilungsstatistiken
- Dokumente-Trend (30 Tage)
- Verarbeitungszeit-Trend (30 Tage)
- Zeitstempel der Generierung

---

## Frontend-Architektur

### Dateien

| Datei | Zweck |
|-------|-------|
| `frontend/src/features/executive/types/executive-types.ts` | TypeScript Interfaces |
| `frontend/src/features/executive/api/executive-api.ts` | API Client (fetch) |
| `frontend/src/features/executive/hooks/useExecutiveData.ts` | TanStack Query Hooks |
| `frontend/src/features/executive/components/KPICard.tsx` | Einzelne KPI-Karte |
| `frontend/src/features/executive/components/TrendChart.tsx` | Line Chart (recharts) |
| `frontend/src/features/executive/components/DepartmentBreakdown.tsx` | Abteilungs-Tabelle |
| `frontend/src/features/executive/components/ExportButton.tsx` | PDF-Export (print) |
| `frontend/src/features/executive/components/ExecutiveDashboard.tsx` | Haupt-Dashboard |
| `frontend/src/features/executive/index.ts` | Barrel Exports |
| `frontend/src/app/routes/executive.tsx` | TanStack Router Route |

### Komponenten-Hierarchie

```
ExecutiveDashboard
├── Header + ExportButton
├── KPI Cards Grid (5 Cards)
│   ├── KPICard (Dokumente/Monat)
│   ├── KPICard (Verarbeitungszeit)
│   ├── KPICard (OCR-Genauigkeit)
│   ├── KPICard (Kosten/Dokument)
│   └── KPICard (Ausstehende Prüfungen)
├── Trend Charts Grid (2 Charts)
│   ├── TrendChart (Dokumenten-Trend)
│   └── TrendChart (Verarbeitungszeit-Trend)
└── DepartmentBreakdown Table
```

### Hooks

```typescript
import { useKPIs, useDepartments, useTrend, useExecutiveSummary } from '@/features/executive'

// KPIs mit Auto-Refresh (5 Minuten)
const kpisQuery = useKPIs()

// Abteilungsstatistiken
const departmentsQuery = useDepartments()

// Trend-Daten
const docTrendQuery = useTrend('documents', 30)
const procTrendQuery = useTrend('processing_time', 30)

// Vollständige Summary
const summaryQuery = useExecutiveSummary()
```

**Query Key Factory**:
```typescript
executiveKeys.all            // ['executive']
executiveKeys.kpis()         // ['executive', 'kpis']
executiveKeys.departments()  // ['executive', 'departments']
executiveKeys.trend(metric, days) // ['executive', 'trend', metric, days]
executiveKeys.summary()      // ['executive', 'summary']
```

### KPICard Props

```typescript
interface KPICardProps {
  title: string                // German label
  value: string | number       // Numeric value or formatted string
  trend?: number               // Percentage (positive = up, negative = down)
  icon: LucideIcon             // Icon component
  iconColor?: string           // Tailwind color class
  format?: 'number' | 'currency' | 'percentage' | 'time'
}
```

**Formatierung**:
- `number` → `1.234` (de-DE)
- `currency` → `1,23 €` (de-DE EUR)
- `percentage` → `96.5%`
- `time` → `1.8s` oder `850ms`

### TrendChart Props

```typescript
interface TrendChartProps {
  title: string
  description?: string
  data: TrendDataPoint[]  // [{date: '2026-01-07', value: 45}]
  valueLabel: string      // Tooltip label
  format?: 'number' | 'currency' | 'percentage' | 'time'
  color?: string          // HSL color
}
```

**Features**:
- Responsive (ResponsiveContainer)
- German date formatting (DD.MM)
- Compact notation for Y-axis
- Hover tooltip mit formatiertem Wert
- Monotone curve interpolation

### DepartmentBreakdown

**Features**:
- shadcn/ui Table
- Badge für OCR-Genauigkeit (Ampel-Logik):
  - ≥95%: `default` (Grün)
  - 85-95%: `secondary` (Gelb)
  - <85%: `destructive` (Rot)
- Badge für ausstehende Dokumente (outline)
- Mono-Font für Zeitangaben

### ExportButton

**Funktion**: Löst `window.print()` aus (Browser öffnet Druckdialog mit PDF-Option)

**Print-Optimierung**:
- Button selbst: `print:hidden`
- Dashboard: Print-spezifischer Footer mit Timestamp

---

## Technische Details

### Backend

**Multi-Tenant Isolation**: Alle Queries filtern nach `company_id` (via `get_current_company_id()`)

**Performance**:
- Read-only Queries (kein Schreibzugriff)
- `COALESCE` für fehlende Werte
- Gruppierung und Aggregation in PostgreSQL
- Auto-Refresh: 5 Minuten (Frontend)

**Trend-Berechnung**:
```python
if docs_last > 0:
    docs_trend = ((docs_current - docs_last) / docs_last) * 100
else:
    docs_trend = 100.0 if docs_current > 0 else 0.0
```

**Kostenschätzung**: `(processing_duration_ms / 1000) * 0.10 EUR/s`

### Frontend

**Auto-Refresh**:
```typescript
staleTime: 5 * 60 * 1000       // 5 Minuten
refetchInterval: 5 * 60 * 1000 // Auto-Refresh alle 5 Minuten
```

**Animationen** (framer-motion):
- Staggered entrance für KPI Cards
- Fade-in für Charts und Tabelle

**Responsive Grid**:
- KPIs: 1 Column (Mobile) → 5 Columns (Desktop)
- Charts: 1 Column (Mobile) → 2 Columns (Desktop)

---

## Integration

### Router-Registrierung (app/main.py)

```python
from app.api.v1.reporting import router as reporting_router

app.include_router(reporting_router, prefix="/api/v1")
```

### Navigation hinzufügen

Beispiel für Sidebar/Menu:
```typescript
{
  title: "Geschäftsführung",
  href: "/executive",
  icon: BarChart3,
  requiresAdmin: true, // Optional: Nur für Admins sichtbar
}
```

---

## Abhängigkeiten

### Backend (bereits vorhanden)
- FastAPI
- SQLAlchemy 2.0 (async)
- Pydantic v2
- structlog

### Frontend (bereits vorhanden)
- React 18
- TanStack Router
- TanStack Query
- shadcn/ui (Card, Table, Badge, Alert, Skeleton, Button)
- Tailwind CSS
- lucide-react (Icons)
- framer-motion (Animationen)

### Neue Abhängigkeit
- **recharts** - Für Line Charts

Installation:
```bash
cd frontend
npm install recharts
```

---

## Testing

### Backend Tests

```python
# tests/unit/services/reporting/test_executive_dashboard_service.py

import pytest
from datetime import datetime, timezone, timedelta
from app.services.reporting import get_kpis, get_department_breakdown, get_trend

@pytest.mark.asyncio
async def test_get_kpis(db_session, test_company, test_documents):
    """Test KPI retrieval."""
    kpis = await get_kpis(company_id=test_company.id, db=db_session)

    assert kpis.documents_this_month >= 0
    assert kpis.documents_last_month >= 0
    assert kpis.avg_processing_time_ms >= 0
    assert 0 <= kpis.ocr_accuracy <= 1
    assert kpis.cost_per_document >= 0

@pytest.mark.asyncio
async def test_get_department_breakdown(db_session, test_company):
    """Test department statistics."""
    departments = await get_department_breakdown(company_id=test_company.id, db=db_session)

    assert isinstance(departments, list)
    for dept in departments:
        assert dept.department
        assert dept.document_count >= 0
        assert 0 <= dept.accuracy <= 1

@pytest.mark.asyncio
async def test_get_trend_invalid_metric(db_session, test_company):
    """Test trend with invalid metric."""
    with pytest.raises(ValueError):
        await get_trend(
            company_id=test_company.id,
            metric="invalid",
            days=30,
            db=db_session
        )
```

### Frontend Tests

```typescript
// frontend/src/features/executive/__tests__/ExecutiveDashboard.test.tsx

import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ExecutiveDashboard } from '../components/ExecutiveDashboard'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }) => (
  <QueryClientProvider client={queryClient}>
    {children}
  </QueryClientProvider>
)

test('renders dashboard title', async () => {
  render(<ExecutiveDashboard />, { wrapper })

  expect(screen.getByText('Geschäftsführung Dashboard')).toBeInTheDocument()
})

test('displays loading skeletons', () => {
  render(<ExecutiveDashboard />, { wrapper })

  const skeletons = screen.getAllByTestId(/skeleton/i)
  expect(skeletons.length).toBeGreaterThan(0)
})
```

---

## Erweiterungsmöglichkeiten

### Weitere KPIs
- Fehlerrate (% fehlgeschlagener Verarbeitungen)
- Durchsatz (Dokumente/Stunde)
- Speichernutzung (Total GB)
- GPU-Auslastung (bei GPU-OCR)

### Zusätzliche Trends
- Fehlerrate-Trend
- Kosten-Trend (absolut)
- Backend-Nutzung (DeepSeek vs. GOT-OCR vs. Surya)

### Filter
- Datumsbereich-Selektor (Custom Range)
- Abteilungs-Filter (Dropdown)
- Vergleich mehrerer Zeiträume

### Export-Optionen
- CSV-Export (raw data)
- Excel-Export mit Charts
- Automatische Reports (E-Mail)

### Echtzeit
- WebSocket-Integration für Live-Updates
- Alert-Benachrichtigungen bei Schwellwerten

---

## Sicherheit

**Authentifizierung**: Alle Endpoints erfordern `get_current_user`
**Authorization**: Multi-Tenant Isolation via `company_id`
**Rate Limiting**: Sollte via Middleware konfiguriert werden
**Logging**: Alle Zugriffe werden via structlog protokolliert (ohne PII)

---

## Performance-Optimierung

### Backend
- **Indexe prüfen**: `company_id`, `created_at`, `status`, `document_type`
- **Materialized Views**: Für KPIs bei sehr großen Datenmengen (>100k Dokumente)
- **Caching**: Redis für KPIs (TTL: 5 Minuten)

### Frontend
- **Code Splitting**: Route-based (automatisch via TanStack Router)
- **Lazy Loading**: Charts nur laden wenn sichtbar (optional)
- **Debouncing**: Bei Filter-Änderungen

---

## Wartung

### Backend
- Service: `app/services/reporting/executive_dashboard_service.py`
- Schemas: `app/api/schemas/reporting.py`
- Router: `app/api/v1/reporting.py`

### Frontend
- Komponenten: `frontend/src/features/executive/components/`
- Hooks: `frontend/src/features/executive/hooks/`
- API: `frontend/src/features/executive/api/`

### Logs
- Backend: structlog mit Kontext (user_id, company_id, metric)
- Frontend: TanStack Query DevTools für Query-Debugging

---

## Checkliste für Deployment

- [ ] Backend:
  - [ ] Router in `app/main.py` registrieren
  - [ ] Indizes auf DB prüfen (`company_id`, `created_at`)
  - [ ] Tests schreiben und ausführen

- [ ] Frontend:
  - [ ] `recharts` installieren (`npm install recharts`)
  - [ ] Route in Navigation hinzufügen
  - [ ] Print-Stylesheet testen (PDF-Export)
  - [ ] Responsive Design auf Mobile testen

- [ ] Dokumentation:
  - [ ] API-Docs in Swagger/OpenAPI prüfen
  - [ ] User-Dokumentation schreiben (Screenshot + Anleitung)

---

**Version**: 1.0
**Erstellt**: 2026-02-06
**Status**: Production-Ready (nach Router-Registrierung + recharts-Installation)

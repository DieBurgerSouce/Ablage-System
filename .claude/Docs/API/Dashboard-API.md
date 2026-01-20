# Personalized Dashboards API

**Status**: Production-Ready
**Version**: 1.0
**Endpoint-Prefix**: `/api/v1/dashboards`

## Überblick

Enterprise-Level Dashboard-Management mit vollständiger Widget-Konfiguration, Layout-Persistierung, Role-based Sharing und Favoriten-System.

### Features

- ✅ Dashboard CRUD (Create, Read, Update, Delete)
- ✅ Widget Management (Add, Remove, Configure)
- ✅ Grid-Layout System (12-Spalten, react-grid-layout kompatibel)
- ✅ Dashboard Sharing (Role-based + User-specific)
- ✅ Favoriten-System
- ✅ Dashboard-Duplikation
- ✅ Preset/Template System
- ✅ Permission-basierte Widget-Filterung

---

## API Endpoints

### Dashboard CRUD

#### `GET /api/v1/dashboards`
Listet alle eigenen Dashboards (optional inkl. geteilte).

**Query Parameters:**
- `include_shared` (bool, default: true) - Mit mir geteilte Dashboards einbeziehen

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Mein Dashboard",
    "description": "Beschreibung",
    "is_default": true,
    "is_favorite": false,
    "is_shared": false,
    "widget_count": 5,
    "created_at": "2026-01-19T12:00:00Z",
    "updated_at": "2026-01-19T12:00:00Z",
    "source": "own"
  }
]
```

---

#### `POST /api/v1/dashboards`
Erstellt ein neues Dashboard.

**Request Body:**
```json
{
  "name": "Mein Dashboard",
  "description": "Beschreibung (optional)",
  "is_default": false,
  "columns": 12,
  "row_height": 80,
  "compact_type": "vertical",
  "widgets": [
    {
      "widget_type": "document_count",
      "x": 0,
      "y": 0,
      "w": 4,
      "h": 3
    }
  ]
}
```

**Response:** `201 Created` + Dashboard-Objekt

---

#### `GET /api/v1/dashboards/{dashboard_id}`
Ruft ein spezifisches Dashboard ab.

**Response:**
```json
{
  "id": "uuid",
  "name": "Mein Dashboard",
  "description": "Beschreibung",
  "is_default": true,
  "is_favorite": false,
  "is_shared": false,
  "columns": 12,
  "row_height": 80,
  "compact_type": "vertical",
  "default_date_range": "30d",
  "default_company_id": null,
  "created_at": "2026-01-19T12:00:00Z",
  "updated_at": "2026-01-19T12:00:00Z",
  "shared_with_count": 0,
  "widgets": [
    {
      "id": "widget-uuid",
      "widget_type": "document_count",
      "x": 0,
      "y": 0,
      "w": 4,
      "h": 3,
      "minW": null,
      "minH": null,
      "maxW": null,
      "maxH": null,
      "config": {},
      "title_override": null,
      "filter_overrides": null,
      "is_visible": true,
      "is_collapsed": false,
      "sort_order": 0
    }
  ]
}
```

---

#### `PATCH /api/v1/dashboards/{dashboard_id}`
Aktualisiert Dashboard-Einstellungen (Partial Update).

**Request Body (alle Felder optional):**
```json
{
  "name": "Neuer Name",
  "description": "Neue Beschreibung",
  "is_default": true,
  "columns": 12,
  "row_height": 80,
  "compact_type": "vertical",
  "default_date_range": "7d",
  "default_company_id": "company-uuid"
}
```

**Response:** Dashboard-Objekt

---

#### `DELETE /api/v1/dashboards/{dashboard_id}`
Löscht ein Dashboard.

**Rules:**
- Mindestens ein Dashboard muss existieren
- Nur eigene Dashboards können gelöscht werden

**Response:** `204 No Content`

**Errors:**
- `400` - Letztes Dashboard kann nicht gelöscht werden

---

### Dashboard Actions

#### `POST /api/v1/dashboards/{dashboard_id}/duplicate`
Dupliziert ein Dashboard.

**Query Parameters:**
- `name` (string, optional) - Name für die Kopie (default: "{Original-Name} (Kopie)")

**Response:** `201 Created` + Dashboard-Objekt

---

#### `PATCH /api/v1/dashboards/{dashboard_id}/favorite`
Setzt oder entfernt Dashboard als Favorit.

**Query Parameters:**
- `is_favorite` (bool, required) - true = Favorit setzen, false = entfernen

**Response:** Dashboard-Objekt

---

### Sharing

#### `POST /api/v1/dashboards/{dashboard_id}/share`
Teilt ein Dashboard mit anderen Usern oder Rollen.

**Request Body:**
```json
{
  "user_ids": ["user-uuid-1", "user-uuid-2"],
  "roles": ["editor", "viewer"],
  "permissions": "view"
}
```

**Fields:**
- `user_ids` (array, optional) - User-IDs zum Teilen
- `roles` (array, optional) - Rollen zum Teilen (role-based sharing)
- `permissions` (string, default: "view") - "view" oder "edit"

**Response:**
```json
{
  "dashboard_id": "uuid",
  "shared_with_users": ["user-uuid-1"],
  "shared_with_roles": ["editor"],
  "success": true,
  "message": "Dashboard erfolgreich geteilt"
}
```

---

#### `DELETE /api/v1/dashboards/{dashboard_id}/share/{user_id}`
Entfernt Sharing für einen bestimmten User.

**Response:** `204 No Content`

---

#### `GET /api/v1/dashboards/shared`
Listet alle mit mir geteilten Dashboards auf.

**Response:** Array von Dashboard-List-Items mit `source="shared"`

---

### Layout Management

#### `PATCH /api/v1/dashboards/{dashboard_id}/layout`
Aktualisiert das komplette Layout (Batch-Update für alle Widget-Positionen).

**Use Case:** Drag & Drop, Resize Events

**Request Body:**
```json
{
  "widgets": [
    {
      "i": "widget-uuid",
      "x": 0,
      "y": 0,
      "w": 4,
      "h": 3,
      "minW": 2,
      "minH": 2,
      "maxW": 12,
      "maxH": 10,
      "static": false
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Layout aktualisiert"
}
```

---

### Widget Management

#### `GET /api/v1/dashboards/widgets/available`
Listet alle verfügbaren Widget-Typen für den aktuellen User.

**Response:**
```json
[
  {
    "widget_type": "document_count",
    "display_name": "Dokument-Anzahl",
    "description": "Zeigt die Anzahl der Dokumente nach Kategorien",
    "requires_permission": false,
    "required_permissions": null,
    "default_size": {
      "w": 4,
      "h": 3
    }
  },
  {
    "widget_type": "invoice_summary",
    "display_name": "Rechnungsübersicht",
    "description": "Übersicht über offene und bezahlte Rechnungen",
    "requires_permission": true,
    "required_permissions": ["finance.invoices.view"],
    "default_size": {
      "w": 6,
      "h": 4
    }
  }
]
```

---

#### `POST /api/v1/dashboards/{dashboard_id}/widgets`
Fügt ein neues Widget zum Dashboard hinzu.

**Request Body:**
```json
{
  "widget_type": "document_count",
  "position": {
    "i": "",
    "x": 0,
    "y": 0,
    "w": 4,
    "h": 3
  },
  "config": {
    "chart_type": "bar",
    "time_range": "30d"
  },
  "title_override": "Meine Dokumente"
}
```

**Response:** `201 Created` + Widget-Objekt

**Errors:**
- `403` - Keine Berechtigung für diesen Widget-Typ
- `404` - Dashboard nicht gefunden

---

#### `PATCH /api/v1/dashboards/{dashboard_id}/widgets/{widget_id}`
Aktualisiert Widget-Konfiguration (Partial Update).

**Request Body (alle Felder optional):**
```json
{
  "position": {
    "i": "widget-uuid",
    "x": 4,
    "y": 0,
    "w": 6,
    "h": 4
  },
  "config": {
    "chart_type": "pie"
  },
  "title_override": "Neuer Titel",
  "is_visible": true,
  "is_collapsed": false
}
```

**Response:** Widget-Objekt

---

#### `DELETE /api/v1/dashboards/{dashboard_id}/widgets/{widget_id}`
Entfernt ein Widget vom Dashboard.

**Response:** `204 No Content`

---

### Presets/Templates

#### `GET /api/v1/dashboards/presets`
Listet verfügbare Dashboard-Presets/Templates auf.

**Query Parameters:**
- `category` (string, optional) - Filter nach Kategorie (default, finance, admin)

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Admin Dashboard",
    "description": "Vollständiges Dashboard für Administratoren",
    "category": "default",
    "for_roles": ["admin"],
    "preview_image_url": null,
    "widget_count": 6
  }
]
```

---

#### `POST /api/v1/dashboards/from-preset/{preset_id}`
Erstellt ein Dashboard von einem Preset/Template.

**Query Parameters:**
- `name` (string, optional) - Name für das neue Dashboard

**Response:** `201 Created` + Dashboard-Objekt

---

## Widget-Typen

### Standard Widgets (keine Berechtigung erforderlich)

| Widget-Typ | Beschreibung | Default-Größe |
|------------|--------------|---------------|
| `today` | Heutige Aufgaben und Ereignisse | 4x3 |
| `quick_links` | Schnellzugriff auf häufige Aktionen | 4x3 |

### Dokument-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `document_count` | - | Anzahl Dokumente nach Kategorien | 4x3 |
| `recent_documents` | `documents.view` | Zuletzt hochgeladene Dokumente | 6x4 |
| `upload` | `documents.create` | Dokument-Upload Widget | 6x4 |
| `ocr_quality` | `documents.view` | OCR-Qualitätsmetriken | 6x3 |

### Finanz-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `invoice_summary` | `finance.invoices.view` | Rechnungsübersicht | 6x4 |
| `finance_status` | `finance.view` | Finanzielle Kennzahlen | 6x3 |
| `open_invoices` | `finance.invoices.view` | Liste offener Rechnungen | 8x5 |
| `cashflow_chart` | `finance.reports.view` | Cashflow-Diagramm | 8x4 |
| `aging_report` | `finance.reports.view` | Fälligkeitsübersicht | 6x4 |

### Business-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `entity_list` | `documents.view` | Geschäftspartner-Liste | 8x5 |
| `risk_overview` | `finance.reports.view` | Risiko-Scores | 6x4 |

### Admin-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `system_status` | `admin.system.view` | System-Metriken | 4x3 |

### Workflow-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `workflow_status` | `documents.view` | Status laufender Workflows | 4x3 |

### Custom-Widgets

| Widget-Typ | Berechtigung | Beschreibung | Default-Größe |
|------------|--------------|--------------|---------------|
| `custom_chart` | - | Benutzerdefinierte Datenvisualisierung | 6x4 |

---

## Grid-System

### Layout-Konfiguration

- **Spalten (columns)**: 1-24 (default: 12)
- **Zeilenhöhe (row_height)**: 20-200px (default: 80px)
- **Kompaktierung (compact_type)**: `vertical`, `horizontal`, `null`

### Widget-Positionen

```typescript
interface LayoutItem {
  i: string;        // Widget-ID
  x: number;        // X-Position (0-11 in 12-column grid)
  y: number;        // Y-Position
  w: number;        // Breite in Grid-Einheiten (1-12)
  h: number;        // Höhe in Grid-Einheiten (1-10)
  minW?: number;    // Minimale Breite (optional)
  minH?: number;    // Minimale Höhe (optional)
  maxW?: number;    // Maximale Breite (optional)
  maxH?: number;    // Maximale Höhe (optional)
  static?: boolean; // Widget kann nicht bewegt/resized werden (optional)
}
```

### Best Practices

1. **Auto-Platzierung**: Wenn keine `position` angegeben wird, wird das Widget automatisch platziert
2. **Responsive Design**: Nutze `minW` und `minH` um sicherzustellen, dass Widgets lesbar bleiben
3. **Performance**: Bei >20 Widgets pro Dashboard, `compact_type: null` nutzen
4. **Batch-Updates**: Für Drag & Drop immer `PATCH /layout` nutzen, nicht einzelne Widget-Updates

---

## Permissions

### Widget-Permissions

Widgets werden automatisch basierend auf User-Berechtigungen gefiltert:

```python
# Admin
permissions = [
    "admin.system.view",
    "finance.view",
    "finance.invoices.view",
    "finance.reports.view",
    "documents.view",
    "documents.create",
]

# Editor
permissions = [
    "finance.view",
    "finance.invoices.view",
    "documents.view",
    "documents.create",
]

# Viewer
permissions = [
    "documents.view",
]
```

### Dashboard-Sharing Permissions

- **Owner**: Volle Kontrolle (Edit, Delete, Share)
- **Shared (edit)**: Widget-Konfiguration ändern, keine Layout-Änderungen
- **Shared (view)**: Nur Ansicht, keine Änderungen

---

## Error Responses

### Standard Error Format

```json
{
  "detail": "Dashboard nicht gefunden"
}
```

### HTTP Status Codes

| Code | Bedeutung |
|------|-----------|
| `200` | Success |
| `201` | Created |
| `204` | No Content (bei DELETE) |
| `400` | Bad Request (z.B. letzte Dashboard kann nicht gelöscht werden) |
| `403` | Forbidden (keine Berechtigung für Widget-Typ) |
| `404` | Not Found (Dashboard/Widget nicht gefunden) |
| `422` | Validation Error (ungültige Request-Daten) |

---

## Migration: is_favorite Support

**Optional Migration**: `108_add_dashboard_favorites_sharing.py`

Fügt hinzu:
- `is_favorite` Spalte in `user_dashboards`
- `dashboard_shares` Tabelle für user-spezifisches Sharing

**Ausführen:**
```bash
alembic upgrade 108_dashboard_enhancements
```

---

## Frontend Integration

### react-grid-layout Kompatibilität

Die API ist vollständig kompatibel mit react-grid-layout:

```typescript
import GridLayout from "react-grid-layout";

const layout = dashboard.widgets.map(w => ({
  i: w.id,
  x: w.x,
  y: w.y,
  w: w.w,
  h: w.h,
  minW: w.minW,
  minH: w.minH,
  maxW: w.maxW,
  maxH: w.maxH,
  static: false,
}));

<GridLayout
  layout={layout}
  cols={dashboard.columns}
  rowHeight={dashboard.rowHeight}
  compactType={dashboard.compact_type}
  onLayoutChange={handleLayoutChange}
>
  {dashboard.widgets.map(widget => (
    <div key={widget.id}>
      <WidgetRenderer widget={widget} />
    </div>
  ))}
</GridLayout>
```

### Layout-Änderungen speichern

```typescript
const handleLayoutChange = async (newLayout: Layout[]) => {
  const widgets = newLayout.map(item => ({
    i: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
  }));

  await fetch(`/api/v1/dashboards/${dashboardId}/layout`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ widgets }),
  });
};
```

---

## Examples

### Vollständiger Dashboard-Workflow

```typescript
// 1. Dashboard erstellen
const dashboard = await fetch('/api/v1/dashboards', {
  method: 'POST',
  body: JSON.stringify({
    name: 'Mein Dashboard',
    columns: 12,
    row_height: 80,
  }),
}).then(r => r.json());

// 2. Widget hinzufügen
const widget = await fetch(`/api/v1/dashboards/${dashboard.id}/widgets`, {
  method: 'POST',
  body: JSON.stringify({
    widget_type: 'document_count',
    position: { i: '', x: 0, y: 0, w: 4, h: 3 },
  }),
}).then(r => r.json());

// 3. Dashboard mit anderen teilen
await fetch(`/api/v1/dashboards/${dashboard.id}/share`, {
  method: 'POST',
  body: JSON.stringify({
    roles: ['editor'],
    permissions: 'view',
  }),
});

// 4. Als Favorit setzen
await fetch(`/api/v1/dashboards/${dashboard.id}/favorite?is_favorite=true`, {
  method: 'PATCH',
});
```

---

## Production Notes

### Performance

- **Caching**: Dashboard-Layouts werden nicht gecacht (immer fresh von DB)
- **Pagination**: Nicht implementiert (max. 50 Dashboards pro User erwartet)
- **Widget-Lazy-Loading**: Frontend sollte Widgets on-demand laden

### Security

- **RLS**: Multi-Tenant-Isolation via User-ID
- **Permission-Check**: Widgets werden automatisch gefiltert
- **Input-Validation**: Alle Inputs werden validiert (Pydantic)
- **SQL-Injection**: Parametrized Queries (SQLAlchemy)

### Future Enhancements

- [ ] Dashboard-Versionierung (Rollback zu früheren Versionen)
- [ ] Widget-Templates (vorkonfigurierte Widgets)
- [ ] Dashboard-Export/Import (JSON)
- [ ] Real-time Collaboration (WebSocket)
- [ ] Dashboard-Analytics (welche Widgets werden am meisten genutzt)

---

**Version**: 1.0
**Letzte Aktualisierung**: 2026-01-19

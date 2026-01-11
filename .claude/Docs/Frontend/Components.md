# Reusable UI Components

> Extrahiert aus `.claude/CLAUDE.md` - AUTO-MANAGED Sektion
> Letzte Aktualisierung: 2026-01-11

---

## Core Components

### EditableField Component

**Path**: `components/ui/editable-field.tsx`

- **Purpose**: Click-to-edit pattern for inline metadata editing
- **Features**: Auto-save with debounce, keyboard navigation, Zod validation, visual save indicators
- **Types**: text, number, date, currency, email
- **Usage**: Document metadata editing, invoice fields, entity properties
- **Key Props**: `value`, `onSave`, `type`, `schema`, `autoSaveDelay`

### EnterpriseDataTable Component

**Path**: `components/ui/data-table/EnterpriseDataTable.tsx`

- **Purpose**: Advanced data table with enterprise features
- **Features**: Sorting, filtering, pagination, grouping, column visibility, export (CSV/Excel), row selection
- **Built on**: TanStack Table v8 with full type safety
- **Usage**: All data-heavy dashboards (AI decisions, reports, validation queues)
- **Key Props**: `columns`, `data`, `enableGrouping`, `enableExport`, `onRowClick`

### MultiStepForm Component

**Path**: `components/forms/MultiStepForm.tsx`

- **Purpose**: Generic multi-step wizard with validation, persistence, and animations
- **Features**: Step-by-step navigation, Zod validation per step, SessionStorage persistence (with 500KB limit + auto-cleanup), dirty state warnings, keyboard navigation
- **Enterprise Fix**: QuotaExceededError prevention with size checks and old-wizard cleanup
- **Usage**: Employee onboarding, workflow creation, multi-page forms
- **Key Props**: `steps`, `onComplete`, `persistKey`, `schema`, `initialData`

---

## Components by Feature

| Feature | Component | Path | Purpose |
|---------|-----------|------|---------|
| **Ablage** | MoveFolderDialog | `ablage/components/MoveFolderDialog.tsx` | Bulk move documents to different categories (WCAG 2.1 AA) |
| **Ablage** | InvoiceTrackingBanner | `ablage/components/InvoiceTrackingBanner.tsx` | Payment status overview (open/due soon/overdue) with Skonto detection |
| **Ablage** | ProactiveInsightsBanner | `ablage/components/ProactiveInsightsBanner.tsx` | AI-driven insights (delays, missing docs, duplicate payments) |
| **Ablage** | QuickActionsBar | `ablage/components/QuickActionsBar.tsx` | Context-aware action shortcuts (new transaction, bulk ops, export) |
| **Ablage** | TransactionTimeline | `ablage/components/TransactionTimeline.tsx` | Horizontal business process timeline (Anfrage → Zahlung) |
| **Ablage** | TransactionsView | `ablage/components/TransactionsView.tsx` | Vorgänge overview with search, filter, sort, pagination |
| **Banking** | AgingReportTable | `banking/components/AgingReportTable.tsx` | Receivables/payables aging report with filtering |
| **Banking** | MatchSuggestionCard | `banking/components/reconciliation/MatchSuggestionCard.tsx` | Transaction-invoice match suggestions with confidence scoring |
| **ERP** | SyncDashboard | `erp/components/SyncDashboard.tsx` | ERP sync status, history, manual sync triggers |
| **Forms** | MultiStepForm | `components/forms/MultiStepForm.tsx` | Generic wizard with validation, persistence, animations |
| **GoBD** | ArchiveManagement | `gobd/components/ArchiveManagement.tsx` | Archive management with integrity verification |
| **Reports** | ReportBuilder | `reports/components/ReportBuilder.tsx` | Visual report builder (data source, columns, filters, charts) |
| **Search** | SearchPanel | `search/components/SearchPanel.tsx` | Controlled search with URL sync, saved searches |
| **Search** | SearchAutocomplete | `search/components/SearchAutocomplete.tsx` | Query suggestions and recent searches |
| **Viewer** | InlineMetadataEditor | `viewer/components/InlineMetadataEditor.tsx` | Document metadata editing panel with EditableField |
| **Workflows** | DelayNode | `workflows/components/nodes/DelayNode.tsx` | ReactFlow node for time delays |

---

## Patterns

### Controlled Components

```typescript
// SearchPanel uses controlled props (value/onChange)
<SearchPanel
  value={{ query, mode, filters }}
  onChange={(updates) => updateURL(updates)}
  onReset={() => clearURL()}
/>

// EditableField provides async save with error handling
<EditableField
  value={document.invoiceNumber}
  onSave={async (value) => await updateDocument({ invoiceNumber: value })}
  label="Rechnungsnummer"
  type="text"
/>
```

---

## Accessibility Standards

- All tables use semantic `<table>`, `<thead>`, `<tbody>` with `scope` attributes
- ARIA labels for screen readers (e.g., `aria-label="Dokumentensuche"`)
- Keyboard navigation support (Enter=Save, Escape=Cancel)
- High contrast support across all 4 display modes
- German loading states: `<Loader2 /> "Lade Daten..."`
- German error states: `<AlertCircle /> "Ein Fehler ist aufgetreten"`

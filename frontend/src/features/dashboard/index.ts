/**
 * Dashboard Feature Module
 *
 * Exports alle Dashboard-relevanten Komponenten, Hooks und APIs.
 */

// API
export * from './api';

// Hooks
export {
  useDefaultDashboard,
  useDashboardList,
  useDashboard,
  useAvailableWidgets,
  useTemplates,
  useCreateDashboard,
  useUpdateDashboard,
  useDeleteDashboard,
  useUpdateLayout,
  useAddWidget,
  useUpdateWidget,
  useRemoveWidget,
  useApplyTemplate,
} from './hooks/useDashboard';

export {
  useWidgetPermissions,
  useCanViewWidget,
  type PermissionFilteredWidget,
} from './hooks/useWidgetPermissions';

export {
  useWidgetConfig,
  type WidgetSettings,
  type WidgetConfigResponse,
} from './hooks/useWidgetConfig';

export {
  useWidgetExport,
  type ExportFormat,
  type ExportOptions,
  type ExportResult,
  type UseWidgetExportReturn,
} from './hooks/useWidgetExport';

// Registry
export {
  widgetRegistry,
  WIDGET_REGISTRY,
  normalizeWidgetType,
  getWidgetComponent,
  getWidgetLabel,
  getWidgetDefinition,
  getAllWidgets,
  getWidgetsByCategory,
  type WidgetRegistryEntry,
} from './registry';

// Store
export {
  useDashboardStore,
  DASHBOARD_PRESETS,
  GRID_COLUMNS,
  type WidgetItem,
  type UserRole,
  type DashboardPreset,
} from './stores/useDashboardStore';

// Components
export { DashboardGrid } from './components/DashboardGrid';
export { DashboardGridEnhanced } from './components/DashboardGridEnhanced';
export { SortableWidget } from './components/SortableWidget';
export { ResizableWidget } from './components/ResizableWidget';
export { WidgetCatalogDrawer } from './components/WidgetCatalogDrawer';
export { WidgetPreviewCard } from './components/WidgetPreviewCard';
export { PresetSelector } from './components/PresetSelector';
export { ActivityFeed, ActivityFeedWidget } from './components/ActivityFeed';
export { WidgetConfigModal } from './components/WidgetConfigModal';
export { WidgetSyncStatus } from './components/WidgetSyncStatus';
export { WidgetExportButton, DashboardExportButton } from './components/WidgetExportButton';

// Mobile Components
export { MobileDashboard } from './MobileDashboard';

// Config
export {
  ALL_LAYOUT_TEMPLATES,
  DEFAULT_LAYOUTS_BY_ROLE,
  DEFAULT_WIDGET_CONFIGS,
  ROLE_HIERARCHY,
  getDefaultLayoutForRole,
  getAvailableTemplatesForRole,
  getTemplateById,
  getTemplatesByTag,
  hasMinRole,
  type LayoutTemplate,
} from './config/defaultLayoutTemplates';
